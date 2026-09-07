from typing import Optional
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.model import Model, ModelVersion, ModelHeartbeat


class ModelRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> Model:
        model = Model(**data)
        self.db.add(model)
        await self.db.flush()
        return model

    async def get_by_id(self, model_id: int) -> Optional[Model]:
        result = await self.db.execute(
            select(Model).where(Model.id == model_id, Model.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_all(self, provider: Optional[str] = None, status: Optional[str] = None) -> list[Model]:
        stmt = select(Model).where(Model.deleted_at.is_(None))
        if provider:
            stmt = stmt.where(Model.provider == provider)
        if status:
            stmt = stmt.where(Model.status == status)
        stmt = stmt.order_by(Model.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, model_id: int, data: dict) -> Optional[Model]:
        stmt = update(Model).where(Model.id == model_id).values(**data).returning(Model)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, model_id: int) -> None:
        await self.db.execute(
            update(Model).where(Model.id == model_id).values(deleted_at=func.now())
        )

    async def create_version(self, data: dict) -> ModelVersion:
        version = ModelVersion(**data)
        self.db.add(version)
        await self.db.flush()
        return version

    async def get_versions(self, model_id: int) -> list[ModelVersion]:
        result = await self.db.execute(
            select(ModelVersion).where(ModelVersion.model_id == model_id, ModelVersion.deleted_at.is_(None))
            .order_by(ModelVersion.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_heartbeat(self, data: dict) -> ModelHeartbeat:
        hb = ModelHeartbeat(**data)
        self.db.add(hb)
        await self.db.flush()
        return hb

    async def get_latest_heartbeat(self, model_id: int) -> Optional[ModelHeartbeat]:
        result = await self.db.execute(
            select(ModelHeartbeat).where(ModelHeartbeat.model_id == model_id)
            .order_by(ModelHeartbeat.checked_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()