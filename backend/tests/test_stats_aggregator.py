"""测试 Token 统计天聚合：_aggregate_daily 的 days 参数行为与幂等重算。"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

from sqlalchemy import delete
from sqlalchemy.sql.dml import Delete

from app.tasks import stats_aggregator as agg
from app.models.token import TokenStatsDaily
from tests.helpers import mock_orm

# 固定"当前时间"，避免测试依赖真实时钟（_to_local 被 patch 为返回该值）
FIXED_LOCAL = datetime(2026, 1, 15, 12, 0)
TODAY = date(2026, 1, 15)


class FakeSession:
    """记录 execute/add/commit 调用的假异步会话；select 返回可配置行集。

    rows_queue 非空时按调用顺序逐次取行集（用于小时聚合里 model/key/application 三条查询）；
    队列用尽或未提供时统一返回 rows。
    """

    def __init__(self, rows: list | None = None, rows_queue: list | None = None):
        self.executed: list = []
        self.added: list = []
        self.committed = False
        self.rows = rows or []
        self.rows_queue = list(rows_queue) if rows_queue else []

    async def execute(self, stmt):
        self.executed.append(stmt)
        res = MagicMock()
        if isinstance(stmt, Delete):
            res.all.return_value = []
        elif self.rows_queue:
            res.all.return_value = self.rows_queue.pop(0)
        else:
            res.all.return_value = self.rows
        return res

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


class _SessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def patch_env(monkeypatch):
    """固定本地时间并替换 async_session，返回 (fake_session, monkeypatch)。"""
    monkeypatch.setattr(agg, "_to_local", lambda _dt: FIXED_LOCAL)
    fake = FakeSession()
    monkeypatch.setattr(agg, "async_session", lambda: _SessionCtx(fake))
    return fake


@pytest.fixture
def patch_env_hourly(monkeypatch):
    """与 patch_env 同，但允许按查询顺序配置多组行集（小时聚合三条查询）。"""
    def _make(rows_queue):
        monkeypatch.setattr(agg, "_to_local", lambda _dt: FIXED_LOCAL)
        fake = FakeSession(rows_queue=rows_queue)
        monkeypatch.setattr(agg, "async_session", lambda: _SessionCtx(fake))
        return fake
    return _make


def _deleted_dates(fake: FakeSession) -> list[date]:
    """提取所有 delete 语句中按 stats_date 等值过滤的日期参数。"""
    dates: list[date] = []
    for stmt in fake.executed:
        if isinstance(stmt, Delete):
            for v in stmt.compile().params.values():
                if isinstance(v, date):
                    dates.append(v)
    return sorted(dates)


@pytest.mark.asyncio
async def test_aggregate_daily_default_rebuilds_7_days(patch_env):
    """默认（无参数）应与旧行为一致：重算今天起往回共 7 天（含今天）。"""
    fake = patch_env
    await agg._aggregate_daily()

    expected = [TODAY - timedelta(days=i) for i in range(7)]
    assert _deleted_dates(fake) == sorted(expected)
    assert fake.committed is True


@pytest.mark.asyncio
async def test_aggregate_daily_refresh_today_only(patch_env):
    """刷新当天（days=1）：只删除并重算今天一天。"""
    fake = patch_env
    await agg._aggregate_daily(days=1)

    assert _deleted_dates(fake) == [TODAY]


def test_aggregate_daily_task_default_days_7():
    """Celery 任务底层函数 days 缺省为 7：兼容旧 00:10 调度（不传参行为不变）。"""
    run = agg.aggregate_daily_stats.run
    assert run.__defaults__ == (7,)


@pytest.mark.asyncio
async def test_aggregate_daily_inserts_daily_rows(patch_env):
    """有小时数据时：把聚合结果写入 TokenStatsDaily（幂等删除后重插）。"""
    fake = patch_env
    fake.rows = [
        mock_orm(dimension_type="model", dimension_id=7, request_count=3,
                 prompt_tokens=30, completion_tokens=20, total_tokens=50,
                 avg_response_ms=10.5),
    ]

    await agg._aggregate_daily(days=1)

    assert len(fake.added) == 1
    daily: TokenStatsDaily = fake.added[0]
    assert daily.stats_date == TODAY
    assert daily.dimension_type == "model"
    assert daily.dimension_id == 7
    assert daily.total_tokens == 50
    assert daily.request_count == 3
    assert daily.avg_response_ms == 10
    assert fake.committed is True


@pytest.mark.asyncio
async def test_aggregate_daily_no_hourly_rows_no_insert(patch_env):
    """当天还没有小时数据（如凌晨）：不产生空行，也不报错。"""
    fake = patch_env
    fake.rows = []

    await agg._aggregate_daily(days=1)

    assert _deleted_dates(fake) == [TODAY]
    assert fake.added == []
    assert fake.committed is True


# ============================================================
# 小时聚合：model / key / application 三个维度
# ============================================================

@pytest.mark.asyncio
async def test_aggregate_hourly_writes_three_dimensions(patch_env_hourly):
    """小时聚合应产出 model、key、application 三种维度的行（此前只有 model）。"""
    fake = patch_env_hourly([
        [mock_orm(model_id=1, request_count=5, prompt_tokens=50, completion_tokens=10,
                  total_tokens=60, avg_response_ms=120.0)],
        [mock_orm(app_key_id=3, request_count=5, prompt_tokens=50, completion_tokens=10,
                  total_tokens=60, avg_response_ms=120.0)],
        [mock_orm(application_id=2, request_count=5, prompt_tokens=50, completion_tokens=10,
                  total_tokens=60, avg_response_ms=120.0)],
    ])

    await agg._aggregate_hourly(hour_offsets=[0])

    dims = {row.dimension_type: row for row in fake.added}
    assert set(dims) == {"model", "key", "application"}
    assert dims["model"].dimension_id == 1
    assert dims["key"].dimension_id == 3
    assert dims["application"].dimension_id == 2
    for row in fake.added:
        assert row.total_tokens == 60
        assert row.request_count == 5
        assert row.stats_hour == 12          # FIXED_LOCAL 12:00，offset=0
        assert row.stats_date == TODAY
    assert fake.committed is True


@pytest.mark.asyncio
async def test_aggregate_hourly_is_idempotent_delete_then_insert(patch_env_hourly):
    """幂等：先按 (日期, 小时) 删除旧聚合，再插入新行；三条维度查询都要发出去。"""
    fake = patch_env_hourly([[], [], []])

    await agg._aggregate_hourly(hour_offsets=[0])

    assert _deleted_dates(fake) == [TODAY]
    # 1 条 delete + 3 条维度 select
    assert len(fake.executed) == 4
    assert fake.added == []
    assert fake.committed is True
