from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import models, keys, tokens, gateway, finetune, compare, system


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.core.redis import redis_client
    await redis_client.ping()
    yield
    # Shutdown
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

# Register routers
app.include_router(models.router, prefix="/api/v1/models", tags=["模型管理"])
app.include_router(keys.router, prefix="/api/v1/keys", tags=["Key管理"])
app.include_router(tokens.router, prefix="/api/v1/tokens", tags=["Token统计"])
app.include_router(gateway.router, prefix="/api/v1/gateway", tags=["网关管理"])
app.include_router(finetune.router, prefix="/api/v1/finetune", tags=["模型微调"])
app.include_router(compare.router, prefix="/api/v1/compare", tags=["模型对比"])
app.include_router(system.router, prefix="/api/v1/system", tags=["系统管理"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}