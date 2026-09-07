from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.finetune_repo import FinetuneRepo
from app.schemas.finetune import FinetuneTaskCreate, DatasetCreate


class FinetuneService:
    def __init__(self, db: AsyncSession):
        self.repo = FinetuneRepo(db)

    async def create_task(self, data: FinetuneTaskCreate, user: str) -> dict:
        task_data = {
            "name": data.name,
            "base_model_id": data.base_model_id,
            "dataset_id": data.dataset_id,
            "val_dataset_id": data.val_dataset_id,
            "hyper_params": data.hyper_params,
            "status": "pending",
            "created_by": user,
            "updated_by": user,
        }
        task = await self.repo.create_task(task_data)
        return {
            "id": task.id,
            "name": task.name,
            "status": task.status,
            "created_at": task.created_at.isoformat(),
        }

    async def get_task(self, task_id: int) -> Optional[dict]:
        task = await self.repo.get_task_by_id(task_id)
        if not task:
            return None
        return {
            "id": task.id,
            "name": task.name,
            "base_model_id": task.base_model_id,
            "dataset_id": task.dataset_id,
            "hyper_params": task.hyper_params,
            "status": task.status,
            "progress": task.progress,
            "loss_value": float(task.loss_value) if task.loss_value else None,
            "error_message": task.error_message,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "created_by": task.created_by,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    async def list_tasks(self, status: Optional[str] = None) -> list[dict]:
        tasks = await self.repo.get_all_tasks(status)
        return [{"id": t.id, "name": t.name, "status": t.status, "progress": t.progress, "created_at": t.created_at.isoformat()} for t in tasks]

    async def update_task_status(self, task_id: int, status: str, user: str) -> Optional[dict]:
        update_data = {"status": status, "updated_by": user}
        if status == "running":
            update_data["started_at"] = datetime.now(timezone.utc)
        elif status in ("completed", "failed", "cancelled"):
            update_data["finished_at"] = datetime.now(timezone.utc)
        
        task = await self.repo.update_task(task_id, update_data)
        if not task:
            return None
        return {"id": task.id, "status": task.status}

    async def create_dataset(self, data: DatasetCreate, user: str) -> dict:
        dataset_data = {
            "name": data.name,
            "format": data.format,
            "description": data.description,
            "created_by": user,
            "updated_by": user,
        }
        dataset = await self.repo.create_dataset(dataset_data)
        return {"id": dataset.id, "name": dataset.name, "format": dataset.format, "version": dataset.version, "created_at": dataset.created_at.isoformat()}

    async def list_datasets(self) -> list[dict]:
        datasets = await self.repo.get_all_datasets()
        return [{"id": d.id, "name": d.name, "format": d.format, "sample_count": d.sample_count, "version": d.version, "annotation_status": d.annotation_status, "created_at": d.created_at.isoformat()} for d in datasets]