from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# asyncpg 连接绑定创建它的事件循环；celery 任务各自用 asyncio.run 起独立循环，
# 若用默认连接池（跨循环复用连接）会报 "attached to a different loop"——
# 同一 worker 子进程第二次执行定时聚合/预警任务即失败。
# 因此用 NullPool：每次操作新建连接、用完即关，天然避免跨循环复用。
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()