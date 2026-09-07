from datetime import date, datetime
from typing import Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.token import ApiRequestLog, TokenStatsHourly, TokenStatsDaily


class TokenRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_daily_stats(
        self, dimension_type: str, dimension_id: Optional[int],
        start_date: date, end_date: date
    ) -> list[TokenStatsDaily]:
        stmt = select(TokenStatsDaily).where(
            TokenStatsDaily.dimension_type == dimension_type,
            TokenStatsDaily.stats_date.between(start_date, end_date),
        )
        if dimension_id:
            stmt = stmt.where(TokenStatsDaily.dimension_id == dimension_id)
        stmt = stmt.order_by(TokenStatsDaily.stats_date)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_hourly_stats(
        self, dimension_type: str, dimension_id: Optional[int],
        start_date: date, end_date: date
    ) -> list[TokenStatsHourly]:
        stmt = select(TokenStatsHourly).where(
            TokenStatsHourly.dimension_type == dimension_type,
            TokenStatsHourly.stats_date.between(start_date, end_date),
        )
        if dimension_id:
            stmt = stmt.where(TokenStatsHourly.dimension_id == dimension_id)
        stmt = stmt.order_by(TokenStatsHourly.stats_date, TokenStatsHourly.stats_hour)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_summary(
        self, start_date: date, end_date: date, dimension_type: str
    ) -> list[dict]:
        stmt = select(
            TokenStatsDaily.dimension_id,
            func.sum(TokenStatsDaily.total_tokens).label("total_tokens"),
            func.sum(TokenStatsDaily.total_cost).label("total_cost"),
            func.sum(TokenStatsDaily.request_count).label("request_count"),
        ).where(
            TokenStatsDaily.dimension_type == dimension_type,
            TokenStatsDaily.stats_date.between(start_date, end_date),
        ).group_by(TokenStatsDaily.dimension_id)
        result = await self.db.execute(stmt)
        rows = result.all()
        return [{"dimension_id": r[0], "total_tokens": r[1], "total_cost": r[2], "request_count": r[3]} for r in rows]

    async def create_log_batch(self, logs: list[dict]) -> None:
        for log in logs:
            self.db.add(ApiRequestLog(**log))
        await self.db.flush()