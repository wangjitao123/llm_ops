from datetime import datetime, timezone, timedelta, date
from celery import shared_task
from app.tasks.worker import celery_app
from app.core.database import async_session
from app.models.token import TokenStatsHourly, TokenStatsDaily
from sqlalchemy import select, func


@celery_app.task(name="aggregate_hourly_stats")
def aggregate_hourly_stats():
    """Aggregate request logs into hourly statistics."""
    import asyncio
    asyncio.run(_aggregate_hourly())


async def _aggregate_hourly():
    now = datetime.now(timezone.utc)
    last_hour = now - timedelta(hours=1)
    stats_date = last_hour.date()
    stats_hour = last_hour.hour
    
    async with async_session() as session:
        # Aggregate by model
        from app.models.token import ApiRequestLog
        stmt = select(
            ApiRequestLog.model_id,
            func.count().label("request_count"),
            func.sum(ApiRequestLog.prompt_tokens).label("prompt_tokens"),
            func.sum(ApiRequestLog.completion_tokens).label("completion_tokens"),
            func.sum(ApiRequestLog.total_tokens).label("total_tokens"),
            func.avg(ApiRequestLog.response_time_ms).label("avg_response_ms"),
        ).where(
            ApiRequestLog.created_at >= last_hour,
            ApiRequestLog.created_at < now,
            ApiRequestLog.model_id.isnot(None),
        ).group_by(ApiRequestLog.model_id)
        
        result = await session.execute(stmt)
        for row in result.all():
            stats = TokenStatsHourly(
                stats_date=stats_date,
                stats_hour=stats_hour,
                dimension_type="model",
                dimension_id=row.model_id or 0,
                request_count=row.request_count,
                prompt_tokens=row.prompt_tokens or 0,
                completion_tokens=row.completion_tokens or 0,
                total_tokens=row.total_tokens or 0,
                avg_response_ms=int(row.avg_response_ms or 0),
            )
            session.add(stats)
        
        await session.commit()


@celery_app.task(name="aggregate_daily_stats")
def aggregate_daily_stats():
    """Aggregate hourly stats into daily statistics."""
    import asyncio
    asyncio.run(_aggregate_daily())


async def _aggregate_daily():
    yesterday = date.today() - timedelta(days=1)
    
    async with async_session() as session:
        stmt = select(
            TokenStatsHourly.dimension_type,
            TokenStatsHourly.dimension_id,
            func.sum(TokenStatsHourly.request_count).label("request_count"),
            func.sum(TokenStatsHourly.prompt_tokens).label("prompt_tokens"),
            func.sum(TokenStatsHourly.completion_tokens).label("completion_tokens"),
            func.sum(TokenStatsHourly.total_tokens).label("total_tokens"),
            func.avg(TokenStatsHourly.avg_response_ms).label("avg_response_ms"),
        ).where(
            TokenStatsHourly.stats_date == yesterday,
        ).group_by(
            TokenStatsHourly.dimension_type,
            TokenStatsHourly.dimension_id,
        )
        
        result = await session.execute(stmt)
        for row in result.all():
            daily = TokenStatsDaily(
                stats_date=yesterday,
                dimension_type=row.dimension_type,
                dimension_id=row.dimension_id,
                request_count=row.request_count,
                prompt_tokens=row.prompt_tokens or 0,
                completion_tokens=row.completion_tokens or 0,
                total_tokens=row.total_tokens or 0,
                avg_response_ms=int(row.avg_response_ms or 0),
            )
            session.add(daily)
        
        await session.commit()