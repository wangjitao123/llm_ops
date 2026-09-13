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
    # 每天统计聚合：小时 → token_stats_daily（重算近 7 天，兜底晚到的小时数据）
    "aggregate-daily-stats": {
        "task": "aggregate_daily_stats",
        "schedule": crontab(hour=0, minute=10),  # 每天 00:10
        "args": (7,),
    },
    # 每小时刷新"当天"天统计：让总览大屏当天即可看到今日用量。
    # 紧跟 x:05 的小时聚合（x:10 执行）；避开 00:10（hour=1-23），
    # 防止与全量 7 天重算并发删插同一天造成重复行。
    "refresh-today-stats": {
        "task": "aggregate_daily_stats",
        "schedule": crontab(hour="1-23", minute=10),  # 每小时第 10 分钟
        "args": (1,),
    },
    # 用量预警检查
    "check-alert-rules": {
        "task": "check_alert_rules",
        "schedule": crontab(minute="*/10"),  # 每 10 分钟
    },
}