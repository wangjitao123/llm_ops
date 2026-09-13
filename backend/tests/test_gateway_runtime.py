"""统一网关运行时测试：路由路径匹配、目标筛选、策略选择（single/weighted/active_standby）、QPS 限流。"""
import pytest
from unittest.mock import AsyncMock

from tests.helpers import mock_orm

from app.services.gateway_service import GatewayService
from app.services import rate_limiter as rl_mod


# ============================================================
# 工具：构造假路由/目标/模型
# ============================================================

def _model(mid: int, name: str = "qwen", status: str = "online"):
    return mock_orm(id=mid, name=name, status=status, deleted_at=None)


def _target(mid: int, *, weight: int = 1, priority: int = 0):
    return mock_orm(id=mid, model_id=mid, weight=weight, priority=priority, model=_model(mid))


def _route(rid: int, targets, *, path: str = "/v1/chat/completions",
           match_type: str = "exact", strategy: str = "weighted", priority: int = 0):
    return mock_orm(id=rid, name=f"route-{rid}", path_pattern=path, match_type=match_type,
                    strategy=strategy, status="enabled", priority=priority, targets=targets)


def _make_service(routes) -> GatewayService:
    db = AsyncMock()
    svc = GatewayService(db)
    svc.repo.get_enabled_routes_with_models = AsyncMock(return_value=routes)
    return svc


# ============================================================
# 路径匹配
# ============================================================

@pytest.mark.asyncio
async def test_path_match_exact_prefix_regex():
    svc = _make_service([
        _route(1, [_target(1)], path="/only/this", match_type="exact"),
        _route(2, [_target(2)], path="/v1/chat/completions", match_type="prefix"),
        _route(3, [_target(3)], path=r"^/api/v\d/.*", match_type="regex"),
    ])
    # exact
    rid, strat, m = await svc.route_model_for("/only/this", "qwen")
    assert rid == 1 and m.id == 1
    # prefix
    rid, _, m = await svc.route_model_for("/v1/chat/completions/extra", "qwen")
    assert rid == 2 and m.id == 2
    # regex
    rid, _, m = await svc.route_model_for("/api/v1/anything", "qwen")
    assert rid == 3 and m.id == 3


@pytest.mark.asyncio
async def test_no_path_match_falls_back():
    svc = _make_service([_route(1, [_target(1)], path="/v1/chat/completions", match_type="exact")])
    rid, strat, m = await svc.route_model_for("/other/path", "qwen")
    assert (rid, strat, m) == (None, None, None)


@pytest.mark.asyncio
async def test_invalid_regex_never_matches():
    route = mock_orm(id=1, path_pattern="([bad", match_type="regex", strategy="weighted",
                     status="enabled", priority=0, targets=[_target(1)])
    svc = _make_service([route])
    rid, _, m = await svc.route_model_for("/v1/x", "qwen")
    assert (rid, m) == (None, None)


# ============================================================
# 目标筛选：同名 + 在线
# ============================================================

@pytest.mark.asyncio
async def test_candidate_filters_by_name_and_online():
    t1 = mock_orm(id=1, model_id=1, weight=1, priority=0,
                  model=mock_orm(id=1, name="qwen", status="online", deleted_at=None))
    t2 = mock_orm(id=2, model_id=2, weight=1, priority=0,
                  model=mock_orm(id=2, name="deepseek", status="online", deleted_at=None))
    t3 = mock_orm(id=3, model_id=3, weight=1, priority=0,
                  model=mock_orm(id=3, name="qwen", status="offline", deleted_at=None))
    svc = _make_service([_route(10, [t1, t2, t3])])

    # 请求 qwen：只有在线且同名的 t1 可选
    rid, strat, m = await svc.route_model_for("/v1/chat/completions", "qwen")
    assert rid == 10 and m.id == 1


@pytest.mark.asyncio
async def test_route_skipped_when_no_matching_target():
    svc = _make_service([
        _route(1, [_target(1)], path="/v1/a"),
        _route(2, [_target(22)], path="/v1/chat/completions"),
    ])
    rid, _, m = await svc.route_model_for("/v1/chat/completions", "other-model")
    assert rid is None and m is None


# ============================================================
# 策略选择
# ============================================================

@pytest.mark.asyncio
async def test_single_strategy():
    route = _route(5, [_target(9)], strategy="single")
    svc = _make_service([route])
    rid, strat, m = await svc.route_model_for("/v1/chat/completions", "qwen")
    assert rid == 5 and strat == "single" and m.id == 9


@pytest.mark.asyncio
async def test_active_standby_prefers_primary_and_exclude():
    # priority 0 = 主，1 = 备
    p = mock_orm(id=11, model_id=11, weight=1, priority=0, model=_model(11))
    s = mock_orm(id=12, model_id=12, weight=1, priority=1, model=_model(12))
    route = _route(6, [s, p], strategy="active_standby")
    svc = _make_service([route])

    rid, strat, m = await svc.route_model_for("/v1/chat/completions", "qwen")
    assert m.id == 11  # 主

    # 主故障（排除）→ 切备
    rid, strat, m = await svc.route_model_for("/v1/chat/completions", "qwen", exclude_model_id=11)
    assert m.id == 12

    # 主被排除、备离线（不可选）→ 无可用目标
    s_offline = mock_orm(id=12, model_id=12, weight=1, priority=1,
                         model=mock_orm(id=12, name="qwen", status="offline", deleted_at=None))
    route2 = _route(8, [s_offline, p], strategy="active_standby")
    svc.repo.get_enabled_routes_with_models = AsyncMock(return_value=[route2])
    rid, strat, m = await svc.route_model_for("/v1/chat/completions", "qwen", exclude_model_id=11)
    assert m is None


@pytest.mark.asyncio
async def test_weighted_round_robin_by_weight():
    from app.services.gateway_service import _weighted_counters
    _weighted_counters.clear()
    a = mock_orm(id=21, model_id=21, weight=2, priority=0, model=_model(21))
    b = mock_orm(id=22, model_id=22, weight=1, priority=0, model=_model(22))
    svc = _make_service([_route(7, [a, b], strategy="weighted")])

    ids = []
    for _ in range(4):
        _, _, m = await svc.route_model_for("/v1/chat/completions", "qwen")
        ids.append(m.id)
    # 权重 2:1 → A,A,B,A
    assert ids == [21, 21, 22, 21]


# ============================================================
# 限流配置
# ============================================================

@pytest.mark.asyncio
async def test_effective_qps_defaults_when_no_config():
    svc = _make_service([])
    svc.repo.get_rate_limit_config = AsyncMock(return_value=None)
    assert await svc.get_effective_qps_limits() == (5000, 100)


@pytest.mark.asyncio
async def test_effective_qps_from_config():
    cfg = mock_orm(config_key="default", global_qps=200, default_key_qps=20)
    svc = _make_service([])
    svc.repo.get_rate_limit_config = AsyncMock(return_value=cfg)
    assert await svc.get_effective_qps_limits() == (200, 20)


# ============================================================
# QPS 限流（Redis 固定窗口）
# ============================================================

class _Pipe:
    def __init__(self, results):
        self.results = results
        self.commands = []

    def incr(self, key):
        self.commands.append(("incr", key))
        return self

    def expire(self, key, secs):
        self.commands.append(("expire", key, secs))
        return self

    async def execute(self):
        return self.results


class _RedisStub:
    def __init__(self, results=None, raise_on_pipeline=False):
        self.results = results or []
        self.raise_on_pipeline = raise_on_pipeline
        self.last_pipe = None

    def pipeline(self):
        if self.raise_on_pipeline:
            raise RuntimeError("redis down")
        self.last_pipe = _Pipe(self.results)
        return self.last_pipe


@pytest.mark.asyncio
async def test_rate_limit_ok(monkeypatch):
    # 结果排列：global incr, global expire, key incr, key expire
    monkeypatch.setattr(rl_mod, "redis_client", _RedisStub([5, 1, 80, 1]))
    allowed, retry = await rl_mod.check_qps(global_limit=5000, key_id=1, key_limit=100)
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limit_global_exceeded(monkeypatch):
    monkeypatch.setattr(rl_mod, "redis_client", _RedisStub([6001, 1, 1, 1]))
    allowed, retry = await rl_mod.check_qps(global_limit=5000, key_id=1, key_limit=100)
    assert allowed is False and retry == 1


@pytest.mark.asyncio
async def test_rate_limit_key_exceeded(monkeypatch):
    monkeypatch.setattr(rl_mod, "redis_client", _RedisStub([5, 1, 150, 1]))
    allowed, retry = await rl_mod.check_qps(global_limit=5000, key_id=1, key_limit=100)
    assert allowed is False


@pytest.mark.asyncio
async def test_rate_limit_no_limits_allowed_without_redis(monkeypatch):
    monkeypatch.setattr(rl_mod, "redis_client", _RedisStub())
    allowed, retry = await rl_mod.check_qps(global_limit=None, key_id=None, key_limit=None)
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limit_redis_error_fail_open(monkeypatch):
    monkeypatch.setattr(rl_mod, "redis_client", _RedisStub(raise_on_pipeline=True))
    allowed, retry = await rl_mod.check_qps(global_limit=10, key_id=1, key_limit=10)
    assert allowed is True
