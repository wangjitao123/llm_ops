from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.v1 import models, keys, tokens, gateway, finetune, compare, system, proxy, quantization, deployment, perf, pricing


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.core.redis import redis_client
    await redis_client.ping()
    # 首次部署自动建表（由 AUTO_CREATE_TABLES 控制，生产建议迁移工具）
    if settings.auto_create_tables:
        from app.core.init_db import init_models
        await init_models()
    yield
    # Shutdown
    from app.core.http import close_http_client
    await close_http_client()
    await redis_client.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """把 FastAPI 422 校验错误转成平台统一的 ApiResponse 格式，前端能看到具体错误原因。"""
    errors = exc.errors()
    detail = "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}"
        for e in errors
    )
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": f"请求参数校验失败: {detail}"},
    )

# Register routers
app.include_router(models.router, prefix="/api/v1/models", tags=["模型管理"])
app.include_router(keys.router, prefix="/api/v1/keys", tags=["Key管理"])
app.include_router(tokens.router, prefix="/api/v1/tokens", tags=["Token统计"])
app.include_router(gateway.router, prefix="/api/v1/gateway", tags=["网关管理"])
app.include_router(finetune.router, prefix="/api/v1/finetune", tags=["模型微调"])
app.include_router(compare.router, prefix="/api/v1/compare", tags=["模型对比"])
app.include_router(system.router, prefix="/api/v1/system", tags=["系统管理"])
app.include_router(proxy.router, tags=["OpenAI兼容接口"])
app.include_router(quantization.router, prefix="/api/v1/quantization", tags=["模型量化"])
app.include_router(deployment.router, prefix="/api/v1/deployments", tags=["模型部署"])
app.include_router(perf.router, prefix="/api/v1/perf", tags=["模型压测"])
app.include_router(pricing.router, prefix="/api/v1/pricing", tags=["计费单价"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
