"""模型压测任务执行器（Celery，队列 `perf`）。

Phase 1：完整实现任务生命周期（取任务 → 置 running → 解析鉴权 → 翻译参数 → 调引擎 →
入库/失败处理），引擎调用本身在 Phase 2 接入 EvalScope。

设计要点：
  * 必须走 task_async_session（NullPool），避免跨事件循环复用连接
  * 任何异常都要落 status=failed + error_message，不能静默
  * 引擎不可用时给出可操作的错误提示（而不是笼统 500）
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.database import task_async_session as async_session
from app.repositories.model_repo import ModelRepo
from app.repositories.perf_repo import PerfTaskRepo
from app.services.perf_engine import (
    EvalScopeEngine,
    PerfAborted,
    PerfEngineUnavailable,
    PerfRunFailed,
)
from app.tasks.worker import celery_app

logger = logging.getLogger(__name__)

# 错误信息入库时的截断长度
_ERROR_MAX_LEN = 4000


@celery_app.task(bind=True, max_retries=0)
def run_perf_task(self, task_id: int):
    """执行一次压测。不自动重试（压测会打目标模型，重试需人工判断）。"""
    try:
        asyncio.run(_do_run(task_id))
    except Exception as e:  # noqa: BLE001 - 兜底，状态已由内部处理
        logger.error("压测任务 %s 执行异常: %s", task_id, e, exc_info=True)


async def _do_run(task_id: int) -> None:
    async with async_session() as session:
        repo = PerfTaskRepo(session)
        task = await repo.get_by_id(task_id)
        if task is None:
            logger.error("压测任务 %s 不存在", task_id)
            return
        if task.status != "pending":
            logger.warning("压测任务 %s 状态为 %s，跳过执行", task_id, task.status)
            return

        started = datetime.now(timezone.utc)
        task = await repo.update(
            task_id,
            {
                "status": "running",
                "started_at": started,
                "progress_sent": 0,
                "error_message": None,
            },
        )
        await repo.add_log(task_id, "info", f"开始执行，目标 {task.target_url}")
        await session.commit()

        try:
            api_key = await _resolve_api_key(session, task)
            tokenizer_path = await _resolve_tokenizer(session, task)

            # 经网关但没配平台 Key → 网关 401，EvalScope 只会报
            # "TimeoutError: Test connection failed"，完全看不出是鉴权问题
            if task.via_gateway and not api_key:
                raise PerfRunFailed(
                    "经网关压测但未配置 PERF_GATEWAY_API_KEY，网关会返回 401。"
                    "请在 deploy/.env 配置平台 AppKey 后重启 perf-worker，"
                    "或改用直连模式。"
                )

            # random 数据集必须有 tokenizer（EvalScope 用它把输入/输出切到指定 token 长度）。
            # 在这里拦一道，避免白跑一次子进程才报错。
            if task.dataset_type == "random" and not tokenizer_path:
                raise PerfRunFailed(
                    "random 数据集需要 tokenizer，但该任务没有配置 tokenizer_path，"
                    "且模型未设置 hf_model_id。请在新建压测时填写 tokenizer_path"
                    "（HuggingFace 仓库名，如 Qwen/Qwen2.5-7B-Instruct），"
                    "或在模型管理里补 hf_model_id。"
                )

            await repo.add_log(
                task_id,
                "info",
                f"开始压测：mode={task.mode} dataset={task.dataset_type} "
                f"target={task.target_url}"
                + (f" tokenizer={tokenizer_path}" if tokenizer_path else ""),
            )
            await session.commit()

            # 引擎内部以子进程执行 EvalScope，并自行回写进度/响应中止
            engine = EvalScopeEngine()
            result = await asyncio.to_thread(engine.run, task, api_key, tokenizer_path)

            await _persist_success(repo, task_id, result, started)
            await session.commit()

        except PerfAborted as e:
            await _persist_cancelled(repo, task_id, str(e), started)
            await session.commit()
            logger.warning("压测任务 %s 已中止", task_id)

        except PerfEngineUnavailable as e:
            await _persist_failure(repo, task_id, str(e), started)
            await session.commit()
            logger.error("压测任务 %s 引擎不可用: %s", task_id, e)

        except PerfRunFailed as e:
            await _persist_failure(repo, task_id, str(e), started)
            await session.commit()
            logger.error("压测任务 %s 执行失败: %s", task_id, e)

        except Exception as e:  # noqa: BLE001 - 任何异常都要落状态
            await _persist_failure(repo, task_id, str(e), started)
            await session.commit()
            logger.error("压测任务 %s 失败: %s", task_id, e, exc_info=True)


async def _resolve_api_key(session, task) -> Optional[str]:
    """解析压测请求要带的鉴权 Key。

    * 经网关：用平台 API Key（settings.perf_gateway_api_key）
    * 直连模型：用模型自身的 api_key_encrypted
    """
    if task.via_gateway:
        return settings.perf_gateway_api_key or None
    if not task.model_id:
        return None
    model = await ModelRepo(session).get_by_id(task.model_id)
    if model is None:
        return None
    return model.api_key_encrypted or None


async def _resolve_tokenizer(session, task) -> Optional[str]:
    """解析 tokenizer 路径（random 数据集必需）。

    优先级：
      1. 任务上显式填写的 tokenizer_path（HF 仓库名或容器内本地目录）
      2. 模型的 model_config.hf_model_id（HF 仓库名，EvalScope 会自动下载）
    """
    explicit = (getattr(task, "tokenizer_path", None) or "").strip()
    if explicit:
        return explicit

    if not task.model_id:
        return None
    model = await ModelRepo(session).get_by_id(task.model_id)
    if model is None:
        return None
    cfg = model.model_config if isinstance(model.model_config, dict) else {}
    hf_id = (cfg or {}).get("hf_model_id") or ""
    return hf_id.strip() or None


async def _persist_success(repo: PerfTaskRepo, task_id: int, result: dict, started: datetime) -> None:
    """把引擎返回的指标写入任务（摘要列 + 全量 JSONB）。"""
    finished = datetime.now(timezone.utc)
    metrics = (result or {}).get("metrics") or {}
    percentiles = (result or {}).get("percentiles") or {}

    await repo.update(
        task_id,
        {
            "status": "completed",
            "finished_at": finished,
            "duration_seconds": int((finished - started).total_seconds()),
            "progress_sent": metrics.get("total_requests") or 0,
            "progress_total": metrics.get("total_requests") or 0,
            "ttft_mean_ms": metrics.get("ttft_mean"),
            "tpot_mean_ms": metrics.get("tpot_mean"),
            "output_throughput": metrics.get("output_throughput"),
            "request_throughput": metrics.get("request_throughput"),
            "success_rate": metrics.get("success_rate"),
            "success_count": metrics.get("success_count"),
            "ttft_p99_ms": (percentiles.get("ttft") or {}).get("p99"),
            "result_json": result,
            "error_message": None,
        },
    )
    report = (result or {}).get("report_path")
    await repo.add_log(
        task_id,
        "ok",
        f"压测完成，指标已入库" + (f"；HTML 报告：{report}" if report else ""),
    )


async def _persist_cancelled(
    repo: PerfTaskRepo, task_id: int, message: str, started: datetime
) -> None:
    """中止：状态 cancelled（区别于 failed，前端不显示为异常）。"""
    finished = datetime.now(timezone.utc)
    await repo.update(
        task_id,
        {
            "status": "cancelled",
            "finished_at": finished,
            "duration_seconds": int((finished - started).total_seconds()),
            "error_message": message or "已被用户中止",
        },
    )
    await repo.add_log(task_id, "warn", message or "已被用户中止")


async def _persist_failure(
    repo: PerfTaskRepo, task_id: int, message: str, started: datetime
) -> None:
    finished = datetime.now(timezone.utc)
    await repo.update(
        task_id,
        {
            "status": "failed",
            "finished_at": finished,
            "duration_seconds": int((finished - started).total_seconds()),
            "error_message": (message or "未知错误")[:_ERROR_MAX_LEN],
        },
    )
    await repo.add_log(task_id, "err", (message or "未知错误")[:_ERROR_MAX_LEN])
