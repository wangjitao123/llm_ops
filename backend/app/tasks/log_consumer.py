import json
from datetime import datetime, timezone
from app.tasks.worker import celery_app
from app.core.database import async_session
from app.models.token import ApiRequestLog


@celery_app.task(name="process_request_log")
def process_request_log(log_data: str):
    """Process a single request log entry."""
    import asyncio
    asyncio.run(_process_log(json.loads(log_data)))


async def _process_log(data: dict):
    async with async_session() as session:
        log = ApiRequestLog(
            request_id=data.get("request_id", ""),
            app_key_id=data.get("app_key_id"),
            model_id=data.get("model_id"),
            route_rule_id=data.get("route_rule_id"),
            request_path=data.get("request_path", ""),
            request_method=data.get("request_method", "POST"),
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("prompt_tokens", 0) + data.get("completion_tokens", 0),
            response_time_ms=data.get("response_time_ms", 0),
            status_code=data.get("status_code", 200),
            client_ip=data.get("client_ip"),
            created_at=datetime.now(timezone.utc),
        )
        session.add(log)
        await session.commit()


@celery_app.task(name="batch_process_logs")
def batch_process_logs(logs_json: str):
    """Batch process multiple request log entries."""
    import asyncio
    logs = json.loads(logs_json)
    asyncio.run(_batch_process(logs))


async def _batch_process(logs: list[dict]):
    async with async_session() as session:
        for data in logs:
            log = ApiRequestLog(
                request_id=data.get("request_id", ""),
                app_key_id=data.get("app_key_id"),
                model_id=data.get("model_id"),
                request_path=data.get("request_path", ""),
                request_method=data.get("request_method", "POST"),
                prompt_tokens=data.get("prompt_tokens", 0),
                completion_tokens=data.get("completion_tokens", 0),
                total_tokens=data.get("prompt_tokens", 0) + data.get("completion_tokens", 0),
                response_time_ms=data.get("response_time_ms", 0),
                status_code=data.get("status_code", 200),
                client_ip=data.get("client_ip"),
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
        await session.commit()