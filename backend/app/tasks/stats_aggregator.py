from datetime import datetime, timezone, timedelta, date
from celery import shared_task
from app.tasks.worker import celery_app
from app.core.database import task_async_session as async_session
from app.models.key import AppKey
from app.models.pricing import ModelPricing
from app.models.token import TokenStatsHourly, TokenStatsDaily, ApiRequestLog
from sqlalchemy import select, func, delete

# 时区：服务器容器 TZ=Asia/Shanghai；日志 created_at 存 UTC（TIMESTAMPTZ）。
# 统计按"东八区自然小时/自然日"切窗，避免 UTC/本地日期错位。
LOCAL_TZ = timezone(timedelta(hours=8))


def _cost_expr():
    """单行请求的计费表达式（元）。

    费用 = 输入 token × 输入单价 + 输出 token × 输出单价，单价口径是「元 / 千 token」，
    所以整体再除以 1000。未配置价格的模型用 COALESCE(..., 0) → 计 0 元。

    这样写的好处：cost 对 token 是线性的，所以可以直接在 SQL 里 SUM，
    即使按 Key / 应用聚合（跨多个模型）也能一条 SQL 算完，不用回表逐行算。
    """
    return (
        ApiRequestLog.prompt_tokens * func.coalesce(ModelPricing.input_price_per_1k, 0)
        + ApiRequestLog.completion_tokens * func.coalesce(ModelPricing.output_price_per_1k, 0)
    ) / 1000


def _to_cost(value) -> float:
    """SUM 可能返回 None（无数据）或 Decimal，统一成 6 位小数 float。"""
    return round(float(value or 0), 6)


def _to_local(dt: datetime) -> datetime:
    """把（可能 naive 或 UTC 的）时间归一为东八区。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


@celery_app.task(name="aggregate_hourly_stats")
def aggregate_hourly_stats(hour_offsets: list[int] | None = None, days_back: int = 0):
    """聚合请求日志到小时统计。

    - 定时调用：无参，聚合最近 1 个完整自然小时；
    - 手动补数：传 hour_offsets=[0,1,2,...]（今天往前第 N 小时）或 days_back。
    """
    import asyncio
    asyncio.run(_aggregate_hourly(hour_offsets=hour_offsets, days_back=days_back))


async def _aggregate_hourly(hour_offsets: list[int] | None = None, days_back: int = 0):
    now_local = _to_local(datetime.now(timezone.utc))
    async with async_session() as session:
        # 确定要聚合的（日期, 小时）窗口
        targets: list[tuple[date, int]] = []
        if hour_offsets:
            for off in hour_offsets:
                t = now_local - timedelta(hours=off)
                targets.append((t.date(), t.hour))
        elif days_back > 0:
            for d in range(days_back, -1, -1):
                t = now_local - timedelta(days=d)
                targets.append((t.date(), t.hour))
        else:
            # 默认：最近 1 个完整自然小时（如现在是 10:40 → 聚合 9 点整段）
            prev_hour = now_local.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            targets.append((prev_hour.date(), prev_hour.hour))

        for stats_date, stats_hour in targets:
            # 窗口：该小时 [date hour:00, +1h)，用 UTC 边界比较
            start_local = datetime(stats_date.year, stats_date.month, stats_date.day, stats_hour, tzinfo=LOCAL_TZ)
            end_local = start_local + timedelta(hours=1)
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            # 幂等：先删掉该小时已有聚合（避免定时+手动重复累加）
            await session.execute(
                delete(TokenStatsHourly).where(
                    TokenStatsHourly.stats_date == stats_date,
                    TokenStatsHourly.stats_hour == stats_hour,
                )
            )

            # ---- 按 model 维度聚合 ----
            stmt = select(
                ApiRequestLog.model_id,
                func.count().label("request_count"),
                func.sum(ApiRequestLog.prompt_tokens).label("prompt_tokens"),
                func.sum(ApiRequestLog.completion_tokens).label("completion_tokens"),
                func.sum(ApiRequestLog.total_tokens).label("total_tokens"),
                func.avg(ApiRequestLog.response_time_ms).label("avg_response_ms"),
                func.sum(_cost_expr()).label("cost"),
            ).select_from(ApiRequestLog).outerjoin(
                ModelPricing, ModelPricing.model_id == ApiRequestLog.model_id
            ).where(
                ApiRequestLog.created_at >= start_utc,
                ApiRequestLog.created_at < end_utc,
                ApiRequestLog.model_id.isnot(None),
            ).group_by(ApiRequestLog.model_id)

            result = await session.execute(stmt)
            for row in result.all():
                session.add(TokenStatsHourly(
                    stats_date=stats_date,
                    stats_hour=stats_hour,
                    dimension_type="model",
                    dimension_id=row.model_id or 0,
                    request_count=row.request_count,
                    prompt_tokens=row.prompt_tokens or 0,
                    completion_tokens=row.completion_tokens or 0,
                    total_tokens=row.total_tokens or 0,
                    total_cost=_to_cost(row.cost),
                    avg_response_ms=int(row.avg_response_ms or 0),
                ))

            # ---- 按 Key 维度聚合（app_key_id → dimension_type='key'） ----
            stmt_key = select(
                ApiRequestLog.app_key_id,
                func.count().label("request_count"),
                func.sum(ApiRequestLog.prompt_tokens).label("prompt_tokens"),
                func.sum(ApiRequestLog.completion_tokens).label("completion_tokens"),
                func.sum(ApiRequestLog.total_tokens).label("total_tokens"),
                func.avg(ApiRequestLog.response_time_ms).label("avg_response_ms"),
                func.sum(_cost_expr()).label("cost"),
            ).select_from(ApiRequestLog).outerjoin(
                ModelPricing, ModelPricing.model_id == ApiRequestLog.model_id
            ).where(
                ApiRequestLog.created_at >= start_utc,
                ApiRequestLog.created_at < end_utc,
                ApiRequestLog.app_key_id.isnot(None),
            ).group_by(ApiRequestLog.app_key_id)

            result_key = await session.execute(stmt_key)
            for row in result_key.all():
                session.add(TokenStatsHourly(
                    stats_date=stats_date,
                    stats_hour=stats_hour,
                    dimension_type="key",
                    dimension_id=row.app_key_id or 0,
                    request_count=row.request_count,
                    prompt_tokens=row.prompt_tokens or 0,
                    completion_tokens=row.completion_tokens or 0,
                    total_tokens=row.total_tokens or 0,
                    total_cost=_to_cost(row.cost),
                    avg_response_ms=int(row.avg_response_ms or 0),
                ))

            # ---- 按应用维度聚合（Key → 所属应用；未绑定应用的 Key 不计入） ----
            stmt_app = (
                select(
                    AppKey.application_id,
                    func.count().label("request_count"),
                    func.sum(ApiRequestLog.prompt_tokens).label("prompt_tokens"),
                    func.sum(ApiRequestLog.completion_tokens).label("completion_tokens"),
                    func.sum(ApiRequestLog.total_tokens).label("total_tokens"),
                    func.avg(ApiRequestLog.response_time_ms).label("avg_response_ms"),
                    func.sum(_cost_expr()).label("cost"),
                )
                .select_from(ApiRequestLog)
                .join(AppKey, AppKey.id == ApiRequestLog.app_key_id)
                .outerjoin(ModelPricing, ModelPricing.model_id == ApiRequestLog.model_id)
                .where(
                    ApiRequestLog.created_at >= start_utc,
                    ApiRequestLog.created_at < end_utc,
                    AppKey.application_id.isnot(None),
                )
                .group_by(AppKey.application_id)
            )

            result_app = await session.execute(stmt_app)
            for row in result_app.all():
                session.add(TokenStatsHourly(
                    stats_date=stats_date,
                    stats_hour=stats_hour,
                    dimension_type="application",
                    dimension_id=row.application_id or 0,
                    request_count=row.request_count,
                    prompt_tokens=row.prompt_tokens or 0,
                    completion_tokens=row.completion_tokens or 0,
                    total_tokens=row.total_tokens or 0,
                    total_cost=_to_cost(row.cost),
                    avg_response_ms=int(row.avg_response_ms or 0),
                ))

        await session.commit()


@celery_app.task(name="aggregate_daily_stats")
def aggregate_daily_stats(days: int = 7):
    """聚合小时统计到天统计（幂等：先删当天再重算）。

    - 每天 00:10 定时调用（days=7）：重算近 7 天，兜底覆盖可能晚到的小时数据；
    - 每小时刷新当天（days=1）：把"今天"已聚合的小时数据滚动进 token_stats_daily，
      使总览大屏/Tok 统计页当天即可看到当日用量（否则当天数据要等次日 00:10 才可见）。
    """
    import asyncio
    asyncio.run(_aggregate_daily(days=days))


async def _aggregate_daily(days: int = 7):
    async with async_session() as session:
        # 重算从今天起往回 days 天（含今天）
        today_local = _to_local(datetime.now(timezone.utc)).date()
        for i in range(days):
            d = today_local - timedelta(days=i)
            await session.execute(
                delete(TokenStatsDaily).where(TokenStatsDaily.stats_date == d)
            )
            stmt = select(
                TokenStatsHourly.dimension_type,
                TokenStatsHourly.dimension_id,
                func.sum(TokenStatsHourly.request_count).label("request_count"),
                func.sum(TokenStatsHourly.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenStatsHourly.completion_tokens).label("completion_tokens"),
                func.sum(TokenStatsHourly.total_tokens).label("total_tokens"),
                func.sum(TokenStatsHourly.total_cost).label("total_cost"),
                func.avg(TokenStatsHourly.avg_response_ms).label("avg_response_ms"),
            ).where(
                TokenStatsHourly.stats_date == d,
            ).group_by(
                TokenStatsHourly.dimension_type,
                TokenStatsHourly.dimension_id,
            )
            result = await session.execute(stmt)
            for row in result.all():
                daily = TokenStatsDaily(
                    stats_date=d,
                    dimension_type=row.dimension_type,
                    dimension_id=row.dimension_id,
                    request_count=row.request_count,
                    prompt_tokens=row.prompt_tokens or 0,
                    completion_tokens=row.completion_tokens or 0,
                    total_tokens=row.total_tokens or 0,
                    total_cost=_to_cost(row.total_cost),
                    avg_response_ms=int(row.avg_response_ms or 0),
                )
                session.add(daily)
        await session.commit()
