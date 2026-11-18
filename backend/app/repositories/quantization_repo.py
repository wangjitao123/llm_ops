from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.quantization import QuantizationTask


class QuantizationRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> QuantizationTask:
        task = QuantizationTask(**data)
        self.db.add(task)
        await self.db.flush()
        return task

    async def get_by_id(self, task_id: int) -> Optional[QuantizationTask]:
        result = await self.db.execute(
            select(QuantizationTask).where(
                QuantizationTask.id == task_id,
                QuantizationTask.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_all(self, status: Optional[str] = None) -> list[QuantizationTask]:
        stmt = select(QuantizationTask).where(QuantizationTask.deleted_at.is_(None))
        if status:
            stmt = stmt.where(QuantizationTask.status == status)
        stmt = stmt.order_by(QuantizationTask.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, task_id: int, data: dict) -> Optional[QuantizationTask]:
        stmt = (
            update(QuantizationTask)
            .where(QuantizationTask.id == task_id)
            .values(**data)
            .returning(QuantizationTask)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, task_id: int) -> bool:
        result = await self.db.execute(
            update(QuantizationTask)
            .where(QuantizationTask.id == task_id)
            .values(deleted_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
            .returning(QuantizationTask.id)
        )
        return result.scalar_one_or_none() is not None