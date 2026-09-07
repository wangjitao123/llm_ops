from typing import Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.finetune import FinetuneTask, Dataset, FinetuneEval, DatasetVersion


class FinetuneRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(self, data: dict) -> FinetuneTask:
        task = FinetuneTask(**data)
        self.db.add(task)
        await self.db.flush()
        return task

    async def get_task_by_id(self, task_id: int) -> Optional[FinetuneTask]:
        result = await self.db.execute(
            select(FinetuneTask).where(FinetuneTask.id == task_id, FinetuneTask.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_all_tasks(self, status: Optional[str] = None) -> list[FinetuneTask]:
        stmt = select(FinetuneTask).where(FinetuneTask.deleted_at.is_(None))
        if status:
            stmt = stmt.where(FinetuneTask.status == status)
        stmt = stmt.order_by(FinetuneTask.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_task(self, task_id: int, data: dict) -> Optional[FinetuneTask]:
        stmt = update(FinetuneTask).where(FinetuneTask.id == task_id).values(**data).returning(FinetuneTask)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_dataset(self, data: dict) -> Dataset:
        dataset = Dataset(**data)
        self.db.add(dataset)
        await self.db.flush()
        return dataset

    async def get_dataset_by_id(self, dataset_id: int) -> Optional[Dataset]:
        result = await self.db.execute(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_all_datasets(self) -> list[Dataset]:
        result = await self.db.execute(
            select(Dataset).where(Dataset.deleted_at.is_(None)).order_by(Dataset.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_dataset_version(self, data: dict) -> DatasetVersion:
        dv = DatasetVersion(**data)
        self.db.add(dv)
        await self.db.flush()
        return dv

    async def get_eval_by_task(self, task_id: int) -> Optional[FinetuneEval]:
        result = await self.db.execute(
            select(FinetuneEval).where(FinetuneEval.task_id == task_id)
        )
        return result.scalar_one_or_none()