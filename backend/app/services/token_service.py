from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.token_repo import TokenRepo


class TokenService:
    def __init__(self, db: AsyncSession):
        self.repo = TokenRepo(db)

    async def get_stats(
        self, dimension_type: str, dimension_id: Optional[int],
        start_date: date, end_date: date, granularity: str = "daily"
    ) -> dict:
        if granularity == "hourly":
            stats = await self.repo.get_hourly_stats(dimension_type, dimension_id, start_date, end_date)
            points = [
                {"date": f"{s.stats_date.isoformat()} {s.stats_hour:02d}:00",
                 "prompt_tokens": s.prompt_tokens, "completion_tokens": s.completion_tokens,
                 "total_tokens": s.total_tokens, "request_count": s.request_count, "cost": float(s.total_cost)}
                for s in stats
            ]
        else:
            stats = await self.repo.get_daily_stats(dimension_type, dimension_id, start_date, end_date)
            points = [
                {"date": s.stats_date.isoformat(),
                 "prompt_tokens": s.prompt_tokens, "completion_tokens": s.completion_tokens,
                 "total_tokens": s.total_tokens, "request_count": s.request_count, "cost": float(s.total_cost)}
                for s in stats
            ]

        total_tokens = sum(p["total_tokens"] for p in points)
        total_cost = sum(p["cost"] for p in points)

        return {
            "dimension_type": dimension_type,
            "dimension_id": dimension_id,
            "points": points,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
        }

    async def get_summary(self, start_date: date, end_date: date, dimension_type: str) -> list[dict]:
        return await self.repo.get_summary(start_date, end_date, dimension_type)

    async def get_cost_report(self, start_date: date, end_date: date, group_by: str) -> dict:
        summary = await self.get_summary(start_date, end_date, group_by)
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "group_by": group_by,
            "items": summary,
            "total_cost": sum(s["total_cost"] for s in summary),
            "total_tokens": sum(s["total_tokens"] for s in summary),
        }