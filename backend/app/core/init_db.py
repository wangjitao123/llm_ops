"""数据库初始化：启动时自动建表（首期无 Alembic 迁移时使用）。

用法：
- 应用启动时：在 lifespan 中调用 init_models()（受 AUTO_CREATE_TABLES 控制）
- 命令行：python -m app.core.init_db

注意：
- create_all 只创建缺失的表，不会修改已存在表结构；
  生产环境结构变更应引入 Alembic 迁移（见 docs/部署/deploy 说明）。
- api_request_log 为分区表（DDL 见 docs/概要设计/数据库设计/sql/01-create-tables.sql），
  create_all 无法生成其分区结构，需另行执行分区 DDL。
"""

import logging

logger = logging.getLogger(__name__)


async def init_models() -> None:
    """依据已注册的 ORM metadata 创建全部缺失的表。"""
    from app.core.database import engine
    from app.models import Base  # noqa: F401  导入以注册 metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured (create_all completed).")


if __name__ == "__main__":
    import asyncio

    asyncio.run(init_models())
    print("Database init completed.")
