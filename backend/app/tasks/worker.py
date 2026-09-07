from celery import Celery
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