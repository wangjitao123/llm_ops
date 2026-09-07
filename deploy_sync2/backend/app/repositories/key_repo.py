from typing import Optional
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.key import AppKey, AppKeyModel, Application


class KeyRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_key(self, data: dict) -> AppKey:
        key = AppKey(**data)
        self.db.add(key)
        await self.db.flush()
        return key

    async def get_by_id(self, key_id: int) -> Optional[AppKey]:
        result = await self.db.execute(
            select(AppKey).where(AppKey.id == key_id, AppKey.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_key_hash(self, key_hash: str) -> Optional[AppKey]:
        result = await self.db.execute(
            select(AppKey).where(AppKey.key_hash == key_hash, AppKey.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_all(self, status: Optional[str] = None) -> list[AppKey]:
        stmt = select(AppKey).where(AppKey.deleted_at.is_(None))
        if status:
            stmt = stmt.where(AppKey.status == status)
        stmt = stmt.order_by(AppKey.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_key(self, key_id: int, data: dict) -> Optional[AppKey]:
        stmt = update(AppKey).where(AppKey.id == key_id).values(**data).returning(AppKey)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_key(self, key_id: int) -> None:
        await self.db.execute(
            update(AppKey).where(AppKey.id == key_id).values(deleted_at=func.now())
        )

    async def set_model_permissions(self, key_id: int, model_ids: list[int]) -> None:
        # 物理删除旧的权限记录（app_key_model 无 deleted_at 列，直接 delete 再插入）
        await self.db.execute(
            delete(AppKeyModel).where(AppKeyModel.app_key_id == key_id)
        )
        for model_id in model_ids:
            perm = AppKeyModel(app_key_id=key_id, model_id=model_id)
            self.db.add(perm)
        await self.db.flush()

    async def get_model_permissions(self, key_id: int) -> list[AppKeyModel]:
        result = await self.db.execute(
            select(AppKeyModel).where(AppKeyModel.app_key_id == key_id)
        )
        return list(result.scalars().all())


class ApplicationRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> Application:
        app = Application(**data)
        self.db.add(app)
        await self.db.flush()
        return app

    async def get_all(self) -> list[Application]:
        result = await self.db.execute(
            select(Application).where(Application.deleted_at.is_(None))
            .order_by(Application.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, app_id: int) -> Optional[Application]:
        result = await self.db.execute(
            select(Application).where(Application.id == app_id, Application.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()