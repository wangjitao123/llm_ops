"""配额校验 + 计费单价 + 费用聚合测试。

分三层：
  1. 纯函数：`check_token_quota` 边界（NULL = 不限、恰好用尽、已超额）
  2. Redis 窗口：`check_key_windows` 的 rpm/rpd 边界与 retry_after（`_incr_window` 打桩）
  3. 真实 SQL：用 SQLite 执行与生产同一段 `_cost_expr()`，验证
     「费用 = 输入×输入价 + 输出×输出价，再除以 1000」以及未配价模型计 0
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Delete

from app.models.pricing import ModelPricing
from app.models.token import ApiRequestLog, TokenStatsHourly
from app.services import rate_limiter as rl
from app.services.rate_limiter import check_key_windows, check_token_quota
from app.tasks import stats_aggregator as agg
from tests.helpers import mock_orm


# ============================================================
# 1. token 配额（纯函数）
# ============================================================

def test_token_quota_null_means_unlimited():
    """未设置配额（NULL / 0）= 不限制。"""
    assert check_token_quota(token_used=10**9, token_quota=None) == (True, 0)
    assert check_token_quota(token_used=10**9, token_quota=0) == (True, 0)


def test_token_quota_partially_used_allowed():
    assert check_token_quota(token_used=999, token_quota=1000) == (True, 0)


def test_token_quota_exhausted_rejected():
    """已用达到上限即拒绝，且 retry_after=0（等多久都不会恢复）。"""
    assert check_token_quota(token_used=1000, token_quota=1000) == (False, 0)
    assert check_token_quota(token_used=1001, token_quota=1000) == (False, 0)


def test_token_quota_none_used_treated_as_zero():
    assert check_token_quota(token_used=None, token_quota=100) == (True, 0)


# ============================================================
# 2. rpm / rpd 窗口（Redis 打桩）
# ============================================================

def _patch_windows(monkeypatch, rpm_used: int, rpd_used: int):
    """把 _incr_window 打桩成按 key 前缀返回固定计数。"""
    calls: list[str] = []

    async def fake_incr(key: str, window_seconds: int) -> int:
        calls.append(key)
        return rpm_used if key.startswith("gw:rpm:") else rpd_used

    monkeypatch.setattr(rl, "_incr_window", fake_incr)
    return calls


@pytest.mark.asyncio
async def test_windows_null_means_unlimited_and_no_redis_call(monkeypatch):
    """两个上限都没配：直接放行，且完全不打 Redis（对存量 Key 零影响）。"""
    calls = _patch_windows(monkeypatch, 10**6, 10**6)
    assert await check_key_windows(key_id=1, rpm_limit=None, rpd_limit=None) == (True, 0)
    assert calls == []


@pytest.mark.asyncio
async def test_rpm_boundary_is_greater_than_not_greater_equal(monkeypatch):
    """rpm 判定用 > ：恰好达到上限仍放行，超出才拒绝。"""
    _patch_windows(monkeypatch, rpm_used=10, rpd_used=0)
    assert (await check_key_windows(key_id=1, rpm_limit=10))[0] is True

    _patch_windows(monkeypatch, rpm_used=11, rpd_used=0)
    allowed, retry = await check_key_windows(key_id=1, rpm_limit=10)
    assert allowed is False
    assert 1 <= retry <= 60          # retry_after 指向下一个分钟边界


@pytest.mark.asyncio
async def test_rpd_rejected_with_retry_to_next_local_day(monkeypatch):
    _patch_windows(monkeypatch, rpm_used=0, rpd_used=101)
    allowed, retry = await check_key_windows(key_id=1, rpd_limit=100)
    assert allowed is False
    assert 1 <= retry <= 86400       # 指向东八区下一个自然日零点


@pytest.mark.asyncio
async def test_both_windows_counted_when_configured(monkeypatch):
    """两个上限都配了就都要计数（不能因为 rpm 先判就跳过 rpd 计数）。"""
    calls = _patch_windows(monkeypatch, rpm_used=1, rpd_used=1)
    await check_key_windows(key_id=7, rpm_limit=10, rpd_limit=100)
    assert any(c.startswith("gw:rpm:7") for c in calls)
    assert any(c.startswith("gw:rpd:7") for c in calls)


@pytest.mark.asyncio
async def test_incr_window_fail_open_on_redis_error(monkeypatch):
    """Redis 异常时窗口计数返回 0（放行），不能把网关整体打成 500。"""
    class BoomRedis:
        def pipeline(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(rl, "redis_client", BoomRedis())
    assert await rl._incr_window("gw:rpm:1", 60) == 0


# ============================================================
# 3. 计费算术（真实 SQLite 执行同一段 SQL）
# ============================================================

def _make_db():
    engine = create_engine("sqlite://")
    ApiRequestLog.__table__.create(engine)
    ModelPricing.__table__.create(engine)
    return engine


def test_cost_expr_real_arithmetic():
    """定价 0.004/0.012 元每千 token；1000 输入 + 500 输出 → 0.004 + 0.006 = 0.010 元。"""
    engine = _make_db()
    with Session(engine) as s:
        s.execute(ModelPricing.__table__.insert().values(
            id=1, model_id=10, input_price_per_1k=Decimal("0.004"),
            output_price_per_1k=Decimal("0.012"), currency="CNY",
        ))
        s.execute(ApiRequestLog.__table__.insert().values(
            id=1, request_id="r1", model_id=10, request_path="/v1/chat/completions",
            request_method="POST", prompt_tokens=1000, completion_tokens=500,
            total_tokens=1500, response_time_ms=10, status_code=200,
        ))
        # 未配价格的模型
        s.execute(ApiRequestLog.__table__.insert().values(
            id=2, request_id="r2", model_id=11, request_path="/v1/chat/completions",
            request_method="POST", prompt_tokens=1000, completion_tokens=1000,
            total_tokens=2000, response_time_ms=10, status_code=200,
        ))
        s.commit()

        stmt = (
            select(ApiRequestLog.model_id, func.sum(agg._cost_expr()).label("cost"))
            .select_from(ApiRequestLog)
            .outerjoin(ModelPricing, ModelPricing.model_id == ApiRequestLog.model_id)
            .group_by(ApiRequestLog.model_id)
        )
        rows = {r.model_id: agg._to_cost(r.cost) for r in s.execute(stmt)}

    assert rows[10] == pytest.approx(0.010, abs=1e-9)
    assert rows[11] == 0.0, "未配置价格的模型必须计 0 元，而不是报错或 NULL"


def test_cost_expr_sums_across_models_for_key_dimension():
    """按 Key 聚合时跨模型求和：每个模型用各自的单价，不能混用。"""
    engine = _make_db()
    with Session(engine) as s:
        s.execute(ModelPricing.__table__.insert().values(
            id=1, model_id=10, input_price_per_1k=Decimal("1.0"),
            output_price_per_1k=Decimal("2.0"), currency="CNY",
        ))
        s.execute(ModelPricing.__table__.insert().values(
            id=2, model_id=11, input_price_per_1k=Decimal("3.0"),
            output_price_per_1k=Decimal("4.0"), currency="CNY",
        ))
        for i, (mid, pt, ct) in enumerate([(10, 1000, 0), (11, 0, 1000)], start=1):
            s.execute(ApiRequestLog.__table__.insert().values(
                id=i, request_id=f"r{i}", app_key_id=5, model_id=mid,
                request_path="/v1/chat/completions", request_method="POST",
                prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct,
                response_time_ms=1, status_code=200,
            ))
        s.commit()

        stmt = (
            select(func.sum(agg._cost_expr()).label("cost"))
            .select_from(ApiRequestLog)
            .outerjoin(ModelPricing, ModelPricing.model_id == ApiRequestLog.model_id)
            .where(ApiRequestLog.app_key_id == 5)
        )
        # 1000/1000*1.0 + 1000/1000*4.0 = 1.0 + 4.0 = 5.0
        assert agg._to_cost(s.execute(stmt).scalar_one()) == pytest.approx(5.0)


def test_to_cost_handles_none_and_rounds():
    assert agg._to_cost(None) == 0.0
    assert agg._to_cost(Decimal("0.123456789")) == 0.123457


# ============================================================
# 4. 聚合器把费用写进统计表
# ============================================================

class FakeSession:
    def __init__(self, rows_queue):
        self.added: list = []
        self.executed: list = []
        self.rows_queue = list(rows_queue)

    async def execute(self, stmt):
        self.executed.append(stmt)
        res = MagicMock()
        if isinstance(stmt, Delete):
            res.all.return_value = []
        else:
            res.all.return_value = self.rows_queue.pop(0) if self.rows_queue else []
        return res

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


class _Ctx:
    def __init__(self, s):
        self.s = s

    async def __aenter__(self):
        return self.s

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_aggregate_hourly_persists_cost(monkeypatch):
    fake = FakeSession([
        [mock_orm(model_id=1, request_count=1, prompt_tokens=10, completion_tokens=5,
                  total_tokens=15, avg_response_ms=1.0, cost=0.25)],
        [mock_orm(app_key_id=2, request_count=1, prompt_tokens=10, completion_tokens=5,
                  total_tokens=15, avg_response_ms=1.0, cost=0.25)],
        [mock_orm(application_id=3, request_count=1, prompt_tokens=10, completion_tokens=5,
                  total_tokens=15, avg_response_ms=1.0, cost=0.25)],
    ])
    monkeypatch.setattr(agg, "async_session", lambda: _Ctx(fake))

    await agg._aggregate_hourly(hour_offsets=[0])

    assert len(fake.added) == 3
    for row in fake.added:
        assert isinstance(row, TokenStatsHourly)
        assert row.total_cost == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_aggregate_daily_sums_cost_from_hourly(monkeypatch):
    fake = FakeSession([
        [mock_orm(dimension_type="model", dimension_id=1, request_count=2,
                  prompt_tokens=20, completion_tokens=10, total_tokens=30,
                  total_cost=Decimal("0.500000"), avg_response_ms=1.0)],
    ])
    monkeypatch.setattr(agg, "async_session", lambda: _Ctx(fake))

    await agg._aggregate_daily(days=1)

    assert len(fake.added) == 1
    assert fake.added[0].total_cost == pytest.approx(0.5)


# ============================================================
# 5. 价格服务序列化
# ============================================================

def test_pricing_response_converts_decimal_to_float():
    from app.services.pricing_service import PricingService

    row = mock_orm(
        model_id=9,
        input_price_per_1k=Decimal("0.004"),
        output_price_per_1k=Decimal("0.012"),
        currency="CNY",
        remark="测试价",
        updated_at=datetime(2026, 1, 1, 0, 0),
        model=mock_orm(id=9, name="Qwen3.8"),
    )
    data = PricingService._to_response(row)
    assert data["model_id"] == 9
    assert data["model_name"] == "Qwen3.8"
    assert data["input_price_per_1k"] == pytest.approx(0.004)
    assert data["output_price_per_1k"] == pytest.approx(0.012)
    assert data["updated_at"] == "2026-01-01T00:00:00"