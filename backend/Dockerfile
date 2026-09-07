FROM python:3.12-slim

WORKDIR /app

# 安装运行时依赖（显式列出，避免依赖本地包构建）
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.30.0" \
    "pydantic>=2.0.0" \
    "pydantic-settings>=2.0.0" \
    "redis>=5.0.0" \
    "celery>=5.4.0" \
    "aio-pika>=9.0.0" \
    "authlib>=1.3.0" \
    "python-jose[cryptography]>=3.3.0" \
    "httpx>=0.27.0" \
    "python-multipart>=0.0.9"

# 复制应用代码
COPY app/ ./app/

# 确保以 /app 为根可导入 app 包
ENV PYTHONPATH=/app
ENV TZ=Asia/Shanghai

EXPOSE 8000

# 运行入口由 compose 覆盖（需先 init_db 建表）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
