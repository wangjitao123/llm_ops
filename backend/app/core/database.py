from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# ============================================================
# 两套 engine 必须分开，原因不同：
#
# 1) API 侧（engine / async_session）—— 用连接池
#    网关是高并发入口，每请求都要鉴权/解析模型。若像 Celery 那样 NullPool
#    （每次新建连接），高并发 + 流式请求长持连接会迅速打满 Postgres
#    max_connections，表现为排队变慢甚至 "too many clients already"。
#
# 2) Celery 侧（task_engine / task_async_session）—— 必须 NullPool
#    asyncpg 连接绑定创建它的事件循环；celery 任务各自用 asyncio.run 起独立
#    循环，若复用连接池里的连接会报 "attached to a different loop"——同一 worker
#    子进程第二次执行定时任务即失败。
# ============================================================

# ---------- API 侧：连接池 ----------
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,  # 取连接前探活，避免拿到被 Postgres 单方面掐掉的死连接
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ---------- Celery 侧：NullPool（跨事件循环安全） ----------
task_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,
)
task_async_session = async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            # 网关代理（流式与非流式）在等上游生成前会主动 close() 归还连接；
            # 此时事务已结束，无需（也不应）再 commit 去多占一次连接。
            if session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
