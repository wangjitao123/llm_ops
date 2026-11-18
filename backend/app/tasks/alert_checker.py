from datetime import datetime, timezone, timedelta, date
from app.tasks.worker import celery_app
from app.core.database import task_async_session as async_session
from app.models.system import AlertRule, AlertLog
from app.models.token import TokenStatsDaily
from sqlalchemy import select, func


@celery_app.task(name="check_alert_rules")
def check_alert_rules():
    """Check all enabled alert rules and trigger alerts if thresholds exceeded."""
    import asyncio
    asyncio.run(_check_rules())


async def _check_rules():
    async with async_session() as session:
        # Get all enabled rules
        result = await session.execute(
            select(AlertRule).where(AlertRule.enabled == True, AlertRule.deleted_at.is_(None))
        )
        rules = result.scalars().all()
        
        today = date.today()
        
        for rule in rules:
            current_value = 0
            
            if rule.metric_type == "daily_token":
                stats = await session.execute(
                    select(func.sum(TokenStatsDaily.total_tokens))
                    .where(TokenStatsDaily.stats_date == today)
                )
                current_value = stats.scalar() or 0
                
            elif rule.metric_type == "monthly_token":
                first_of_month = today.replace(day=1)
                stats = await session.execute(
                    select(func.sum(TokenStatsDaily.total_tokens))
                    .where(TokenStatsDaily.stats_date >= first_of_month)
                )
                current_value = stats.scalar() or 0
                
            elif rule.metric_type == "daily_cost":
                stats = await session.execute(
                    select(func.sum(TokenStatsDaily.total_cost))
                    .where(TokenStatsDaily.stats_date == today)
                )
                current_value = float(stats.scalar() or 0)
            
            if current_value >= rule.threshold_value:
                alert_level = "critical" if current_value >= rule.threshold_value else "warn"
                alert = AlertLog(
                    rule_id=rule.id,
                    alert_level=alert_level,
                    current_value=current_value,
                    threshold_value=rule.threshold_value,
                    message=f"Alert: {rule.name} exceeded threshold. Current: {current_value}, Threshold: {rule.threshold_value}",
                    notified=False,
                )
                session.add(alert)
        
        await session.commit()