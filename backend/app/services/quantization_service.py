from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.quantization_repo import QuantizationRepo
from app.repositories.model_repo import ModelRepo
from app.schemas.quantization import QuantizationTaskCreate, QuantizationTaskResponse
from datetime import datetime, timezone


class QuantizationService:
    def __init__(self, db: AsyncSession):
        self.repo = QuantizationRepo(db)
        self.model_repo = ModelRepo(db)

    async def create_task(self, data: QuantizationTaskCreate, user: str) -> dict:
        task_data = data.model_dump()
        task_data["created_by"] = user
        task = await self.repo.create(task_data)
        return self._to_response(task)

    async def get_task(self, task_id: int) -> Optional[dict]:
        task = await self.repo.get_by_id(task_id)
        if not task:
            return None
        return self._to_response(task)

    async def list_tasks(self, status: Optional[str] = None) -> list[dict]:
        tasks = await self.repo.get_all(status)
        return [self._to_response(t) for t in tasks]

    async def update_task(
        self, task_id: int, status: Optional[str] = None,
        progress: Optional[int] = None, error_message: Optional[str] = None,
        result_model_id: Optional[int] = None, output_path: Optional[str] = None,
    ) -> Optional[dict]:
        update_data = {}
        if status is not None:
            update_data["status"] = status
        if progress is not None:
            update_data["progress"] = progress
        if error_message is not None:
            update_data["error_message"] = error_message
        if result_model_id is not None:
            update_data["result_model_id"] = result_model_id
        if output_path is not None:
            update_data["output_path"] = output_path
        update_data["updated_at"] = datetime.now(timezone.utc)

        task = await self.repo.update(task_id, update_data)
        if not task:
            return None
        return self._to_response(task)

    async def delete_task(self, task_id: int) -> bool:
        return await self.repo.delete(task_id)

    async def submit_quantization(self, task_id: int) -> Optional[dict]:
        """提交量化任务到 Celery worker。"""
        task = await self.repo.get_by_id(task_id)
        if not task:
            return None
        if task.status != "pending":
            return self._to_response(task)

        # 标记为 queued
        task = await self.repo.update(task_id, {
            "status": "queued",
            "updated_at": datetime.now(timezone.utc),
        })

        # 触发 Celery 任务（放 quantization 队列）
        from app.tasks.quantization_runner import run_quantization
        run_quantization.apply_async(args=[task_id], queue="quantization")

        return self._to_response(task)

    async def retry_task(self, task_id: int) -> Optional[dict]:
        """重试失败的任务：重置为 queued 并清空错误信息。"""
        task = await self.repo.get_by_id(task_id)
        if not task:
            return None
        if task.status != "failed":
            return self._to_response(task)
        task = await self.repo.update(task_id, {
            "status": "queued",
            "progress": 0,
            "error_message": None,
            "updated_at": datetime.now(timezone.utc),
        })
        from app.tasks.quantization_runner import run_quantization
        run_quantization.apply_async(args=[task_id], queue="quantization")
        return self._to_response(task)

    def _to_response(self, task) -> dict:
        return {
            "id": task.id,
            "name": task.name,
            "base_model_id": task.base_model_id,
            "hf_model_id": task.hf_model_id,
            "output_name": task.output_name,
            "algorithm": task.algorithm,
            "weight_bits": task.weight_bits,
            "activation_bits": task.activation_bits,
            "group_size": task.group_size,
            "calib_samples": task.calib_samples,
            "calib_source": task.calib_source,
            "calib_text": task.calib_text,
            "output_path": task.output_path,
            "status": task.status,
            "progress": task.progress,
            "error_message": task.error_message,
            "result_model_id": task.result_model_id,
            "created_by": task.created_by,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }