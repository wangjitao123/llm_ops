"""
模型量化 Celery 任务。

在 GPU worker（quantization-worker）上执行：
1. 从 HuggingFace 下载模型
2. 执行量化（GPTQ / AWQ / bitsandbytes）
3. 保存量化后模型到共享卷
4. 更新任务状态 / 进度
"""
import os
import json
import logging
from celery import shared_task
from app.tasks.worker import celery_app

logger = logging.getLogger(__name__)

# 量化模型保存根目录（容器的共享卷挂载点）
MODELS_DIR = os.getenv("QUANTIZED_MODELS_DIR", "/models")


@celery_app.task(
    name="run_quantization",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=7200,  # 2h
    time_limit=10800,       # 3h
)
def run_quantization(self, task_id: int):
    """执行模型量化。"""
    import asyncio

    async def _run():
        from app.core.database import task_async_session as async_session
        async with async_session() as db:
            from app.repositories.quantization_repo import QuantizationRepo
            repo = QuantizationRepo(db)

            task = await repo.get_by_id(task_id)
            if not task:
                logger.error("量化任务 %s 不存在", task_id)
                return

            try:
                # 状态更新：running
                await repo.update(task_id, {"status": "running", "progress": 0})
                await db.commit()

                # 执行量化
                result = await _do_quantize(task)

                # 成功：更新状态
                await repo.update(task_id, {
                    "status": "completed",
                    "progress": 100,
                    "output_path": result.get("output_path"),
                    "result_model_id": result.get("model_id"),
                })
                await db.commit()
                logger.info("量化任务 %s 完成，模型ID=%s", task_id, result.get("model_id"))

            except Exception as exc:
                await repo.update(task_id, {
                    "status": "failed",
                    "error_message": str(exc),
                })
                await db.commit()
                logger.error("量化任务 %s 失败: %s", task_id, exc)

    asyncio.run(_run())


async def _do_quantize(task) -> dict:
    """
    实际的量化流程。根据 task.algorithm 选择不同实现。
    """
    from app.repositories.quantization_repo import QuantizationRepo
    from app.repositories.model_repo import ModelRepo
    from app.core.database import task_async_session as async_session

    algorithm = task.algorithm.lower()
    hf_model_id = task.hf_model_id

    # 输出目录
    safe_name = hf_model_id.replace("/", "--")
    output_dir = os.path.join(
        MODELS_DIR,
        f"{safe_name}-{algorithm}-w{task.weight_bits}a{task.activation_bits}",
    )
    os.makedirs(output_dir, exist_ok=True)

    if algorithm == "gptq":
        _quantize_gptq(task, output_dir)
    elif algorithm == "awq":
        _quantize_awq(task, output_dir)
    elif algorithm == "bitsandbytes":
        _quantize_bnb(task, output_dir)
    else:
        raise ValueError(f"不支持的量化算法: {algorithm}")

    # 量化完成后：在平台注册为模型
    async with async_session() as db:
        model_repo = ModelRepo(db)
        quant_repo = QuantizationRepo(db)

        model_data = {
            "name": task.output_name or f"{task.name} ({algorithm.upper()})",
            "provider": "quantized",
            "version": f"1.0-q{task.weight_bits}a{task.activation_bits}-{algorithm}",
            "api_base_url": f"file://{output_dir}",
            "api_key_encrypted": "",
            "qps_limit": 100,
            "timeout_ms": 60000,
            "weight": 1,
            "status": "active",
            "model_config": {
                "quantized": True,
                "base_model": task.hf_model_id,
                "algorithm": algorithm,
                "weight_bits": task.weight_bits,
                "activation_bits": task.activation_bits,
                "group_size": task.group_size,
            },
            "description": f"通过平台量化生成的 {algorithm.upper()} {task.weight_bits}bit 模型，基座 {hf_model_id}",
            "created_by": task.created_by,
            "updated_by": task.created_by,
        }
        model = await model_repo.create(model_data)
        await db.flush()

        # 更新任务结果
        await quant_repo.update(task.id, {"result_model_id": model.id, "output_path": output_dir})
        await db.commit()

        return {"output_path": output_dir, "model_id": model.id}


def _quantize_gptq(task, output_dir: str):
    """使用 llm-compressor 执行 GPTQ 量化。"""
    try:
        from llmcompressor import compress
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        logger.warning("llm-compressor 未安装，尝试 auto_gptq...")
        _quantize_auto_gptq(task, output_dir)
        return

    import torch

    logger.info("下载模型 %s ...", task.hf_model_id)
    model = AutoModelForCausalLM.from_pretrained(
        task.hf_model_id,
        torch_dtype=torch.float16,
        device_map="auto",
    )
    tokenizer = AutoTokenizer.from_pretrained(task.hf_model_id)

    # 校准数据（使用默认样本）
    calib_data = _get_calibration_data(tokenizer, task.calib_samples, custom_text=task.calib_text if task.calib_source == 'custom' else None)

    logger.info("执行 GPTQ 量化 (group_size=%d, weight_bits=%d)...",
                 task.group_size, task.weight_bits)
    compressed = compress(
        model,
        tokenizer=tokenizer,
        calibration_data=calib_data,
        algorithm="gptq",
        target_bit_width=task.weight_bits,
        group_size=task.group_size,
    )

    logger.info("保存量化模型到 %s ...", output_dir)
    compressed.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # 保存元信息
    with open(os.path.join(output_dir, "quant_config.json"), "w") as f:
        json.dump({
            "algorithm": "gptq",
            "weight_bits": task.weight_bits,
            "activation_bits": task.activation_bits,
            "group_size": task.group_size,
            "base_model": task.hf_model_id,
        }, f, indent=2)


def _quantize_auto_gptq(task, output_dir: str):
    """使用 auto_gptq 作为 GPTQ 实现方案二。"""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

    logger.info("auto_gptq：下载模型 %s ...", task.hf_model_id)
    quantize_config = BaseQuantizeConfig(
        bits=task.weight_bits,
        group_size=task.group_size,
        desc_act=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(task.hf_model_id)
    calib_data = _get_calibration_data(tokenizer, task.calib_samples, custom_text=task.calib_text if task.calib_source == 'custom' else None)

    model = AutoGPTQForCausalLM.from_pretrained(
        task.hf_model_id,
        quantize_config,
        torch_dtype=torch.float16,
        device_map="auto",
    )

    logger.info("auto_gptq：量化中...")
    model.quantize(calib_data, use_triton=False)
    model.save_quantized(output_dir)
    tokenizer.save_pretrained(output_dir)


def _quantize_awq(task, output_dir: str):
    """使用 autoawq 执行 AWQ 量化。"""
    try:
        from awq import AutoAWQForCausalLM
        from transformers import AutoTokenizer
    except ImportError:
        raise ImportError("AWQ 量化需要安装 autoawq: pip install autoawq")

    import torch

    logger.info("AWQ：下载模型 %s ...", task.hf_model_id)
    model = AutoAWQForCausalLM.from_pretrained(
        task.hf_model_id,
        torch_dtype=torch.float16,
        device_map="auto",
    )
    tokenizer = AutoTokenizer.from_pretrained(task.hf_model_id)

    logger.info("AWQ：量化中 (w%d)...", task.weight_bits)
    model.quantize(
        tokenizer=tokenizer,
        quant_config={
            "zero_point": True,
            "q_group_size": task.group_size,
            "w_bit": task.weight_bits,
            "version": "GEMM",
        },
        calib_data=_get_calibration_text(tokenizer, task.calib_samples, custom_text=task.calib_text if task.calib_source == 'custom' else None),
    )

    logger.info("保存 AWQ 模型到 %s ...", output_dir)
    model.save_quantized(output_dir)
    tokenizer.save_pretrained(output_dir)


def _quantize_bnb(task, output_dir: str):
    """使用 bitsandbytes 执行 4/8-bit 量化。"""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=task.weight_bits <= 4,
        load_in_8bit=task.weight_bits > 4,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    logger.info("bitsandbytes：下载并量化 %s ...", task.hf_model_id)
    model = AutoModelForCausalLM.from_pretrained(
        task.hf_model_id,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(task.hf_model_id)

    from transformers import PreTrainedModel
    model.save_pretrained(output_dir, safe_serialization=True)
    tokenizer.save_pretrained(output_dir)

    # bitsandbytes 量化配置文件
    with open(os.path.join(output_dir, "quant_config.json"), "w") as f:
        json.dump({
            "algorithm": "bitsandbytes",
            "weight_bits": task.weight_bits,
            "quant_type": "nf4" if task.weight_bits <= 4 else "int8",
        }, f, indent=2)


def _get_calibration_data(tokenizer, n_samples: int = 256, custom_text: str | None = None):
    """生成用于校准的文本数据。若提供 custom_text 则优先使用。"""
    from datasets import load_dataset
    try:
        if custom_text:
            texts = [line.strip() for line in custom_text.split("\n") if line.strip()]
            texts = texts[:n_samples]
            if not texts:
                raise ValueError("自定义校准文本为空")
        else:
            dataset = load_dataset("wikitext", "wikitext-2-raw-v1", split="train", trust_remote_code=True)
            texts = dataset["text"][:n_samples]
            texts = [t for t in texts if len(t.strip()) > 20]
        return tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=512)
    except Exception as exc:
        logger.warning("加载校准数据集失败: %s，使用随机生成", exc)
        import torch
        return {
            "input_ids": torch.randint(0, 5000, (n_samples, 128)),
            "attention_mask": torch.ones((n_samples, 128)),
        }


def _get_calibration_text(tokenizer, n_samples: int = 256, custom_text: str | None = None):
    """返回校准文本列表（AWQ 格式）。若提供 custom_text 则优先使用。"""
    from datasets import load_dataset
    try:
        if custom_text:
            texts = [line.strip() for line in custom_text.split("\n") if line.strip()]
            texts = texts[:128]
            if not texts:
                raise ValueError("自定义校准文本为空")
        else:
            dataset = load_dataset("wikitext", "wikitext-2-raw-v1", split="train", trust_remote_code=True)
            texts = dataset["text"][:n_samples]
            texts = [t.strip() for t in texts if len(t.strip()) > 20]
        return texts[:128]  # AWQ 通常不需要太多
    except Exception as exc:
        logger.warning("加载校准数据集失败: %s，使用默认样本", exc)
        return [
            "Artificial intelligence has transformed many industries in recent years.",
            "Large language models are powerful tools for natural language processing.",
            "Model quantization reduces memory footprint while maintaining accuracy.",
        ] * 10