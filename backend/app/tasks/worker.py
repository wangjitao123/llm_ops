from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "ai_gateway",
    broker=settings.rabbitmq_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.log_consumer",
        "app.tasks.stats_aggregator",
        "app.tasks.alert_checker",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_soft_time_limit=300,
    task_time_limit=600,
    worker_max_tasks_per_child=1000,
)

# ============================================================
# Celery Beat 定时调度（缺这里 → Token 统计聚合/预警永不触发）
# ============================================================
celery_app.conf.beat_schedule = {
    # 每小时统计聚合：请求日志 → token_stats_hourly
    "aggregate-hourly-stats": {
        "task": "aggregate_hourly_stats",
        "schedule": crontab(minute=5),  # 每小时第 5 分钟
    },
    # 每天统计聚合：小时 → token_stats_daily
    "aggregate-daily-stats": {
        "task": "aggregate_daily_stats",
        "schedule": crontab(hour=0, minute=10),  # 每天 00:10
    },
    # 用量预警检查
    "check-alert-rules": {
        "task": "check_alert_rules",
        "schedule": crontab(minute="*/10"),  # 每 10 分钟
    },
}