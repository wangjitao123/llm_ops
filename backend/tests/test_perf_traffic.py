"""Phase 3：压测流量标记与统计隔离测试（ADR-004 / M04）。

核心契约：
  * `X-Perf-Test` 只抑制 `api_request_log` 写入
  * 鉴权/限流/路由**完全不受影响**（伪造该头拿不到额外配额）
  * 经网关压测时 perf-worker 强制注入该头，用户不可关闭
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.helpers import mock_orm

from app.api.v1 import proxy as proxy_mod
from app.services import perf_engine as engine
from app.services.proxy_service import ProxyService


# ============================================================
# 头部识别
# ============================================================

@pytest.mark.parametrize("value", ["1", "true", "TRUE", " 1 ", "True"])
def test_header_truthy_values(value):
    assert proxy_mod._is_perf_test_request({"x-perf-test": value}) is True


@pytest.mark.parametrize("value", ["0", "false", "", "yes", "2", "on"])
def test_header_falsy_values(value):
    """只认 1/true，其他值一律不算压测（避免 'yes'/'2' 这类被误用）。"""
    assert proxy_mod._is_perf_test_request({"x-perf-test": value}) is False


def test_header_missing_returns_false():
    assert proxy_mod._is_perf_test_request({}) is False
    assert proxy_mod._is_perf_test_request(None) is False


def test_header_case_insensitive_lookup_for_plain_dict():
    assert proxy_mod._is_perf_test_request({"X-Perf-Test": "1"}) is True


def test_header_empty_string_is_false():
    assert proxy_mod._is_perf_test_request({"x-perf-test": ""}) is False


# ============================================================
# 日志抑制
# ============================================================

@pytest.mark.asyncio
async def test_record_request_skipped_for_perf_traffic():
    """压测流量：不写 api_request_log，返回 None。"""
    db = MagicMock()
    db.flush = AsyncMock()
    svc = ProxyService(db, suppress_request_log=True)

    log = await svc.record_request(
        request_id="req_perf",
        app_key_id=1,
        model_id=2,
        request_path="/v1/chat/completions",
        prompt_tokens=100,
        completion_tokens=50,
    )

    assert log is None
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_request_written_for_normal_traffic():
    """普通流量：照常写库。"""
    db = MagicMock()
    db.flush = AsyncMock()
    svc = ProxyService(db)

    log = await svc.record_request(
        request_id="req_normal",
        app_key_id=1,
        model_id=2,
        request_path="/v1/chat/completions",
        prompt_tokens=10,
        completion_tokens=5,
    )

    assert log is not None
    assert log.total_tokens == 15
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_suppress_flag_defaults_to_false():
    """不传参数时默认不抑制 —— 保证既有调用行为不变。"""
    db = MagicMock()
    db.flush = AsyncMock()
    svc = ProxyService(db)
    assert svc.suppress_request_log is False


# ============================================================
# perf-worker 侧强制注入
# ============================================================

def _task(**overrides):
    base = dict(
        mode="closed_loop",
        target_url="http://llm-ops-api:8000/v1",
        model_name_snapshot="qwen-7b",
        dataset_type="random",
        input_length=1024,
        output_length=256,
        stream=True,
        temperature=0.0,
        tokenizer_path=None,
        parallel=10,
        number=100,
        rate=None,
        max_concurrency=None,
        sla_metric=None,
        sla_threshold_ms=None,
        sla_lower_bound=None,
        sla_upper_bound=None,
        turns=None,
        via_gateway=False,
    )
    base.update(overrides)
    return base


def test_via_gateway_injects_perf_header():
    args = engine.build_arguments(_task(via_gateway=True), api_key="sk-platform")
    assert args["headers"]["X-Perf-Test"] == "1"


def test_direct_mode_does_not_inject_perf_header():
    """直连模型不经网关，无需打标（也就不会有原始请求头污染）。"""
    args = engine.build_arguments(_task(via_gateway=False))
    assert "headers" not in args


def test_perf_header_survives_with_other_headers():
    """将来若给用户开放自定义头，压测标记不能被覆盖掉。"""
    args = engine.build_arguments(_task(via_gateway=True))
    assert args["headers"].get("X-Perf-Test") == "1"
