from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perf import PerfTask, PerfTaskLog


class PerfTaskRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> PerfTask:
        task = PerfTask(**data)
        self.db.add(task)
        await self.db.flush()
        return task

    async def get_by_id(self, task_id: int) -> Optional[PerfTask]:
        result = await self.db.execute(
            select(PerfTask).where(
                PerfTask.id == task_id,
                PerfTask.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        status: Optional[str] = None,
        model_id: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> list[PerfTask]:
        stmt = select(PerfTask).where(PerfTask.deleted_at.is_(None))
        if status:
            stmt = stmt.where(PerfTask.status == status)
        if model_id:
            stmt = stmt.where(PerfTask.model_id == model_id)
        if search:
            stmt = stmt.where(PerfTask.name.ilike(f"%{search}%"))
        stmt = stmt.order_by(PerfTask.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, task_id: int, data: dict) -> Optional[PerfTask]:
        data = {**data, "updated_at": datetime.now(timezone.utc)}
        stmt = (
            update(PerfTask)
            .where(PerfTask.id == task_id)
            .values(**data)
            .returning(PerfTask)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, task_id: int) -> bool:
        result = await self.db.execute(
            update(PerfTask)
            .where(PerfTask.id == task_id, PerfTask.deleted_at.is_(None))
            .values(deleted_at=datetime.now(timezone.utc))
            .returning(PerfTask.id)
        )
        return result.scalar_one_or_none() is not None

    async def stats(self) -> dict:
        """统计卡片：总数 / 已完成 / 运行中 / 最近一次 TTFT P99。"""
        base = select(
            func.count(PerfTask.id),
            func.count(PerfTask.id).filter(PerfTask.status == "completed"),
            func.count(PerfTask.id).filter(PerfTask.status == "running"),
        ).where(PerfTask.deleted_at.is_(None))
        row = (await self.db.execute(base)).one()

        latest_ttft = (
            await self.db.execute(
                select(PerfTask.ttft_p99_ms)
                .where(
                    PerfTask.deleted_at.is_(None),
                    PerfTask.status == "completed",
                    PerfTask.ttft_p99_ms.is_not(None),
                )
                .order_by(PerfTask.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        return {
            "total": int(row[0] or 0),
            "completed": int(row[1] or 0),
            "running": int(row[2] or 0),
            "latest_ttft_p99_ms": latest_ttft,
        }

    # ---------- 日志 ----------
    async def add_log(self, task_id: int, level: str, message: str) -> None:
        self.db.add(
            PerfTaskLog(
                task_id=task_id,
                level=level,
                message=message[:4000],
                created_at=datetime.now(timezone.utc),
            )
        )
        await self.db.flush()

    async def get_logs(self, task_id: int, limit: int = 500) -> list[PerfTaskLog]:
        result = await self.db.execute(
            select(PerfTaskLog)
            .where(PerfTaskLog.task_id == task_id)
            .order_by(desc(PerfTaskLog.created_at))
            .limit(limit)
        )
        # 反过来按时间正序返回，便于前端直接渲染
        return list(reversed(result.scalars().all()))
