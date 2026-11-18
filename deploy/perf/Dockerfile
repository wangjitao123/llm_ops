# ============================================================
# 模型压测 Worker —— 独立镜像（装 EvalScope）
#
# 为什么必须独立镜像（见 ADR-002）：
#   evalscope 会连带 modelscope[datasets]、pandas、nltk、sacrebleu、pyarrow 等，
#   塞进 api-server 会把镜像从 ~300MB 撑到 1GB+。
#
# 不需要 GPU：压测是纯 HTTP 负载生成。
#
# ⚠️ 网络提示：evalscope[perf] 的依赖总量约 200MB+（含 jieba 19MB 源码包、
#    modelscope 6MB、pyarrow 40MB）。直连 files.pythonhosted.org 在国内经常
#    15KB/s 甚至超时。**务必通过 PIP_INDEX_URL 指定国内镜像**：
#      PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
#    或 https://pypi.tuna.tsinghua.edu.cn/simple
# ============================================================
FROM python:3.12-slim

WORKDIR /app

# 镜像源与重试策略（空值 = 官方 PyPI）
ARG PIP_INDEX_URL=
ARG PIP_TIMEOUT=180
ARG PIP_RETRIES=20

# ---- 平台公共依赖（与 api-server 一致，缺了 Celery 任务 import 会失败）----
RUN pip install --no-cache-dir \
        --index-url ${PIP_INDEX_URL:-https://pypi.org/simple} \
        --timeout ${PIP_TIMEOUT} --retries ${PIP_RETRIES} \
        "fastapi>=0.115.0" \
        "sqlalchemy[asyncio]>=2.0.0" \
        "asyncpg>=0.30.0" \
        "pydantic>=2.0.0" \
        "pydantic-settings>=2.0.0" \
        "redis>=5.0.0" \
        "celery>=5.4.0" \
        "aio-pika>=9.0.0" \
        "httpx>=0.27.0" \
        "python-multipart>=0.0.9"

# ---- 压测引擎 ----
# EVALSCOPE_VER 留空 = 装最新版。**建议首次构建成功后立即锁定版本**，
# 避免上游 breaking change 打挂平台：
#   docker run --rm llm-ops-perf pip show evalscope | grep Version
#   然后设 .env 里 EVALSCOPE_VER=<版本号> 并重建
ARG EVALSCOPE_VER=
RUN if [ -n "$EVALSCOPE_VER" ]; then \
        pip install --no-cache-dir \
            --index-url ${PIP_INDEX_URL:-https://pypi.org/simple} \
            --timeout ${PIP_TIMEOUT} --retries ${PIP_RETRIES} \
            "evalscope[perf]==$EVALSCOPE_VER"; \
    else \
        pip install --no-cache-dir \
            --index-url ${PIP_INDEX_URL:-https://pypi.org/simple} \
            --timeout ${PIP_TIMEOUT} --retries ${PIP_RETRIES} \
            "evalscope[perf]"; \
    fi

# ---- 应用代码（含 app/tasks/perf_entry.py 子进程入口）----
COPY app/ ./app/

# 压测输出目录（HTML 报告 + 结果库），需与 api-server 共享同一卷
RUN mkdir -p /app/perf_outputs
ENV PERF_OUTPUTS_DIR=/app/perf_outputs
ENV PYTHONPATH=/app
ENV TZ=Asia/Shanghai

# 只消费 perf 队列
CMD ["celery", "-A", "app.tasks.worker:celery_app", "worker", "-Q", "perf", "--concurrency=2", "-l", "info"]
