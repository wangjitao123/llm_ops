# ============================================================
# GPU 量化 Worker — GPTQ / AWQ / bitsandbytes
#
# 基础镜像选择说明：
#   选用 pytorch/pytorch 官方 CUDA 镜像（而非 nvidia/cuda + 手动 pip torch），原因：
#   1. torch 2.4.0 与 CUDA 12.4 / cuDNN 9 的版本组合已由官方验证，无兼容坑；
#   2. Python 3.12 已预装，无需额外配 apt 源（Ubuntu 22.04 默认只有 3.10）；
#   3. auto-gptq / autoawq 需要编译 CUDA 扩展，官方镜像的库路径最省事。
#   代价是镜像较大（解压后约 8GB），但只需构建一次，之后走 Docker 层缓存。
# ============================================================
FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

WORKDIR /app

# 系统依赖（auto-gptq / autoawq 源码编译需要 build-essential）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 项目公共依赖（与 api-server 保持一致，用于连库/连消息队列）
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.30.0" \
    "pydantic>=2.0.0" \
    "pydantic-settings>=2.0.0" \
    "redis>=5.0.0" \
    "celery>=5.4.0" \
    "aio-pika>=9.0.0" \
    "httpx>=0.27.0" \
    "python-multipart>=0.0.9" \
    "nvidia-ml-py>=12.0.0"

# 量化核心依赖（transformers / datasets 用于下载模型与校准数据）
RUN pip install --no-cache-dir \
    "transformers>=4.44.0" \
    "accelerate>=0.33.0" \
    "datasets>=2.20.0" \
    "sentencepiece>=0.2.0"

# 量化算法库：GPTQ / AWQ / bitsandbytes
# llm-compressor 是 GPTQ 的首选实现，装不上时 runner 会自动回退到 auto-gptq
RUN pip install --no-cache-dir \
    "auto-gptq>=0.7.0" \
    "autoawq>=0.2.0" \
    "bitsandbytes>=0.44.0"

# 复制项目后端代码（build context 为 ../backend，故 app/ 即 backend/app/）
COPY app/ ./app/

# 量化模型保存目录（由 compose 挂载共享卷）
RUN mkdir -p /models
ENV QUANTIZED_MODELS_DIR=/models
ENV PYTHONPATH=/app
ENV TZ=Asia/Shanghai

# 量化 worker 入口：只消费 quantization 队列，避免与常规任务抢资源
CMD ["celery", "-A", "app.tasks.worker:celery_app", "worker", "-Q", "quantization", "--concurrency=1", "-l", "info"]
