"""模型压测模块测试（Phase 1：参数层 / 校验层 / 指纹 / 对比）。"""
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock

import pytest

from tests.helpers import mock_orm

from app.core.config import settings
from app.schemas.perf import PerfTaskCreate
from app.services import perf_engine as engine
from app.services.perf_fingerprint import (
    compute_fingerprint,
    diff_fingerprint_fields,
)
from app.services.perf_service import PerfService, PerfValidationError


# ============================================================
# 参数指纹
# ============================================================

def _fp_task(**overrides):
    base = dict(
        model_id=1,
        mode="closed_loop",
        parallel=200,
        rate=None,
        number=2000,
        dataset_type="random",
        input_length=1024,
        output_length=256,
        stream=True,
    )
    base.update(overrides)
    return base


def test_fingerprint_stable_for_same_params():
    assert compute_fingerprint(_fp_task()) == compute_fingerprint(_fp_task())


def test_fingerprint_differs_when_parallel_changes():
    assert compute_fingerprint(_fp_task()) != compute_fingerprint(_fp_task(parallel=100))


def test_fingerprint_ignores_float_int_representation():
    """rate=20 与 rate=20.0 必须同指纹，否则会误判为不可比。"""
    a = compute_fingerprint(_fp_task(mode="open_loop", parallel=None, rate=20, number=3000))
    b = compute_fingerprint(_fp_task(mode="open_loop", parallel=None, rate=20.0, number=3000))
    assert a == b


def test_fingerprint_treats_none_and_missing_as_empty():
    assert compute_fingerprint({"mode": "closed_loop"}) == compute_fingerprint(
        {"mode": "closed_loop", "parallel": None}
    )


def test_fingerprint_distinguishes_stream_flag():
    assert compute_fingerprint(_fp_task(stream=True)) != compute_fingerprint(_fp_task(stream=False))


def test_diff_fingerprint_fields_reports_labels():
    diffs = diff_fingerprint_fields(_fp_task(), _fp_task(parallel=50, input_length=2048))
    assert "并发数" in diffs
    assert "输入长度" in diffs
    assert "总请求数" not in diffs


def test_diff_fingerprint_fields_empty_when_identical():
    assert diff_fingerprint_fields(_fp_task(), _fp_task()) == []


# ============================================================
# Schema 校验
# ============================================================

def _create_payload(**overrides):
    base = dict(
        name="基准压测",
        model_id=1,
        mode="closed_loop",
        parallel=200,
        number=2000,
        dataset_type="random",
        input_length=1024,
        output_length=256,
    )
    base.update(overrides)
    return base


def test_schema_accepts_valid_closed_loop():
    data = PerfTaskCreate(**_create_payload())
    assert data.mode == "closed_loop"


def test_schema_rejects_closed_loop_without_parallel():
    with pytest.raises(ValueError) as e:
        PerfTaskCreate(**_create_payload(parallel=None))
    assert "parallel" in str(e.value)


def test_schema_rejects_open_loop_without_rate():
    with pytest.raises(ValueError) as e:
        PerfTaskCreate(**_create_payload(mode="open_loop", parallel=None, rate=None))
    assert "rate" in str(e.value)


def test_schema_rejects_sla_without_bounds():
    with pytest.raises(ValueError) as e:
        PerfTaskCreate(
            **_create_payload(
                mode="sla",
                parallel=None,
                number=None,
                sla_metric="ttft",
                sla_threshold_ms=500,
                sla_lower_bound=None,
                sla_upper_bound=None,
            )
        )
    assert "sla_lower_bound" in str(e.value)


def test_schema_rejects_sla_inverted_bounds():
    with pytest.raises(ValueError) as e:
        PerfTaskCreate(
            **_create_payload(
                mode="sla",
                parallel=None,
                number=1000,
                sla_metric="ttft",
                sla_threshold_ms=500,
                sla_lower_bound=500,
                sla_upper_bound=100,
            )
        )
    assert "必须大于" in str(e.value)


def test_schema_rejects_multi_turn_without_turns():
    with pytest.raises(ValueError) as e:
        PerfTaskCreate(**_create_payload(mode="multi_turn", turns=None))
    assert "turns" in str(e.value)


def test_schema_rejects_random_without_lengths():
    with pytest.raises(ValueError) as e:
        PerfTaskCreate(**_create_payload(input_length=None))
    assert "input_length" in str(e.value)


def test_schema_rejects_unknown_dataset():
    with pytest.raises(ValueError) as e:
        PerfTaskCreate(**_create_payload(dataset_type="nonsense"))
    assert "数据集" in str(e.value)


def test_schema_allows_non_random_without_lengths():
    """非 random 数据集不强制长度（由数据集自身决定）。"""
    data = PerfTaskCreate(
        **_create_payload(dataset_type="openqa", input_length=None, output_length=None)
    )
    assert data.dataset_type == "openqa"


# ============================================================
# 引擎参数翻译
# ============================================================

def test_build_sla_params_shape():
    assert engine.build_sla_params("ttft", 500) == [{"p99_ttft": "<= 500ms"}]
    assert engine.build_sla_params("tpot", 20) == [{"p99_tpot": "<= 20ms"}]
    assert engine.build_sla_params("latency", 2000) == [{"p99_latency": "<= 2000ms"}]


def test_build_sla_params_rejects_unknown_metric():
    with pytest.raises(ValueError):
        engine.build_sla_params("bogus", 100)


def _engine_task(**overrides):
    base = dict(
        mode="closed_loop",
        target_url="http://m:8000/v1",
        model_name_snapshot="qwen-7b",
        dataset_type="random",
        input_length=1024,
        output_length=256,
        stream=True,
        temperature=0.0,
        tokenizer_path=None,
        parallel=200,
        number=2000,
        rate=None,
        max_concurrency=None,
        sla_metric=None,
        sla_threshold_ms=None,
        sla_lower_bound=None,
        sla_upper_bound=None,
        turns=None,
    )
    base.update(overrides)
    return base


def test_build_arguments_closed_loop():
    args = engine.build_arguments(_engine_task())
    assert args["api"] == "openai"
    assert args["url"] == "http://m:8000/v1/chat/completions"
    assert args["dataset"] == "random"
    assert args["parallel"] == 200
    assert args["number"] == 2000
    assert args["open_loop"] is False
    # random 数据集：min/max 取同值保证长度确定
    assert args["min_prompt_length"] == args["max_prompt_length"] == 1024
    assert args["min_tokens"] == args["max_tokens"] == 256
    assert args["stream"] is True


def test_build_arguments_open_loop():
    args = engine.build_arguments(
        _engine_task(mode="open_loop", parallel=None, rate=20, number=3000, max_concurrency=500)
    )
    assert args["open_loop"] is True
    assert args["rate"] == 20.0
    assert args["number"] == 3000
    assert args["parallel"] == 500  # 连接池上限


def test_build_arguments_sla_uses_bounds_not_steps():
    args = engine.build_arguments(
        _engine_task(
            mode="sla",
            parallel=None,
            number=1000,
            sla_metric="ttft",
            sla_threshold_ms=500,
            sla_lower_bound=50,
            sla_upper_bound=400,
        )
    )
    assert args["sla_auto_tune"] is True
    assert args["sla_variable"] == "parallel"
    assert args["sla_params"] == [{"p99_ttft": "<= 500ms"}]
    assert args["sla_lower_bound"] == 50
    assert args["sla_upper_bound"] == 400


def test_build_arguments_sla_rejects_inverted_bounds():
    with pytest.raises(ValueError):
        engine.build_arguments(
            _engine_task(
                mode="sla",
                parallel=None,
                number=100,
                sla_metric="ttft",
                sla_threshold_ms=500,
                sla_lower_bound=400,
                sla_upper_bound=50,
            )
        )


def test_build_arguments_multi_turn():
    args = engine.build_arguments(
        _engine_task(mode="multi_turn", parallel=50, number=200, turns=5)
    )
    assert args["multi_turn"] is True
    assert args["min_turns"] == args["max_turns"] == 5
    assert args["parallel"] == 50


def test_build_arguments_includes_api_key_when_given():
    args = engine.build_arguments(_engine_task(), api_key="sk-x")
    assert args["api_key"] == "sk-x"

def test_build_arguments_includes_tokenizer_from_param():
    """random 数据集必需 tokenizer：调用方推导后通过参数传入。"""
    args = engine.build_arguments(_engine_task(), tokenizer_path="Qwen/Qwen2.5-7B-Instruct")
    assert args["tokenizer_path"] == "Qwen/Qwen2.5-7B-Instruct"


def test_build_arguments_tokenizer_param_overrides_task():
    task = _engine_task()
    task["tokenizer_path"] = "old/repo"
    args = engine.build_arguments(task, tokenizer_path="new/repo")
    assert args["tokenizer_path"] == "new/repo"


def test_build_arguments_falls_back_to_task_tokenizer():
    task = _engine_task()
    task["tokenizer_path"] = "task/repo"
    args = engine.build_arguments(task)
    assert args["tokenizer_path"] == "task/repo"


def test_build_arguments_omits_tokenizer_when_absent():
    args = engine.build_arguments(_engine_task(), tokenizer_path=None)
    assert "tokenizer_path" not in args


def test_build_arguments_omits_api_key_when_absent():
    args = engine.build_arguments(_engine_task(), api_key=None)
    assert "api_key" not in args


def test_build_arguments_rejects_empty_target_url():
    with pytest.raises(ValueError):
        engine.build_arguments(_engine_task(target_url=""))


def test_build_arguments_does_not_double_append_path():
    args = engine.build_arguments(_engine_task(target_url="http://m:8000/v1/chat/completions"))
    assert args["url"] == "http://m:8000/v1/chat/completions"


def test_engine_reports_unavailable_when_evalscope_missing(monkeypatch):
    monkeypatch.setattr(engine, "engine_available", lambda: (False, "未安装"))
    with pytest.raises(engine.PerfEngineUnavailable) as e:
        engine.EvalScopeEngine().run(_engine_task())
    assert "未安装" in str(e.value)


# ============================================================
# Service 校验层
# ============================================================

def _svc():
    svc = PerfService(AsyncMock())
    svc.repo = AsyncMock()
    svc.model_repo = AsyncMock()
    return svc


def test_hard_restriction_allows_local_provider():
    svc = _svc()
    svc._assert_model_testable(mock_orm(name="qwen-7b", provider="local-vllm"))


def test_no_restriction_by_default(monkeypatch):
    """默认不限制：白名单留空时，任何 provider 都能压测（平台模型都是自建）。"""
    monkeypatch.setattr(settings, "perf_testable_provider_prefix", "")
    svc = _svc()
    for provider in ("openai", "deepseek", "ollama", "", None):
        svc._assert_model_testable(mock_orm(name="m", provider=provider))


def test_restriction_applies_when_whitelist_configured(monkeypatch):
    """显式配置白名单后，不在白名单的 provider 被拒。"""
    monkeypatch.setattr(settings, "perf_testable_provider_prefix", "local-")
    svc = _svc()
    with pytest.raises(PerfValidationError) as e:
        svc._assert_model_testable(mock_orm(name="gpt-4", provider="openai"))
    assert "不在压测白名单" in str(e.value)


def test_limits_reject_parallel_over_max():
    svc = _svc()
    data = PerfTaskCreate(**_create_payload(parallel=settings.perf_max_parallel + 1, number=10))
    with pytest.raises(PerfValidationError) as e:
        svc._assert_limits(data)
    assert "并发数" in str(e.value)


def test_limits_reject_number_over_max():
    svc = _svc()
    data = PerfTaskCreate(
        **_create_payload(parallel=1, number=settings.perf_max_number + 1)
    )
    with pytest.raises(PerfValidationError) as e:
        svc._assert_limits(data)
    assert "请求数" in str(e.value)


def test_limits_accept_within_bounds():
    svc = _svc()
    svc._assert_limits(PerfTaskCreate(**_create_payload(parallel=10, number=100)))


def test_resolve_target_url_direct():
    url = PerfService._resolve_target_url(
        mock_orm(name="m", api_base_url="http://m:8000/v1"), via_gateway=False
    )
    assert url == "http://m:8000/v1/chat/completions"


def test_resolve_target_url_via_gateway_uses_platform():
    url = PerfService._resolve_target_url(
        mock_orm(name="m", api_base_url="http://m:8000/v1"), via_gateway=True
    )
    assert url == f"{settings.perf_gateway_base_url.rstrip('/')}/chat/completions"


def test_resolve_target_url_rejects_missing_base():
    with pytest.raises(PerfValidationError):
        PerfService._resolve_target_url(mock_orm(name="m", api_base_url=""), via_gateway=False)


def test_expected_total_multi_turn_multiplies():
    data = PerfTaskCreate(**_create_payload(mode="multi_turn", parallel=10, number=200, turns=5))
    assert PerfService._expected_total(data) == 1000


def test_expected_total_closed_loop_is_number():
    data = PerfTaskCreate(**_create_payload())
    assert PerfService._expected_total(data) == 2000


# ============================================================
# 对比逻辑
# ============================================================

def _compare_task(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        name="t1",
        created_at=now,
        mode="closed_loop",
        model_name_snapshot="qwen-7b",
        parallel=200,
        rate=None,
        number=2000,
        dataset_type="random",
        input_length=1024,
        output_length=256,
        stream=True,
        fingerprint="abc",
        ttft_mean_ms=142.0,
        ttft_p99_ms=186.0,
        tpot_mean_ms=18.6,
        output_throughput=1284.0,
        request_throughput=20.0,
        success_rate=100.0,
        duration_seconds=161,
        result_json={"percentiles": {"ttft": {"p50": 112, "p90": 158}}},
    )
    base.update(overrides)
    return mock_orm(**base)


def test_compare_item_extracts_percentiles():
    item = PerfService._to_compare_item(_compare_task())
    assert item.ttft_p50_ms == 112
    assert item.ttft_p90_ms == 158
    assert item.ttft_p99_ms == 186.0


def test_compare_item_tolerates_missing_result_json():
    item = PerfService._to_compare_item(_compare_task(result_json=None))
    assert item.ttft_p50_ms is None
    assert item.ttft_p99_ms == 186.0  # 摘要列仍在


def test_compute_deltas_relative_to_first():
    a = PerfService._to_compare_item(_compare_task())
    b = PerfService._to_compare_item(
        _compare_task(id=2, name="t2", ttft_mean_ms=142.0 * 1.5, output_throughput=1284.0 * 0.5)
    )
    deltas = PerfService._compute_deltas([a, b])
    assert deltas["ttft_mean_ms"][0] == 0.0
    assert deltas["ttft_mean_ms"][1] == 50.0
    assert deltas["output_throughput"][1] == -50.0


def test_compute_deltas_handles_zero_base():
    a = PerfService._to_compare_item(_compare_task(success_rate=0.0))
    b = PerfService._to_compare_item(_compare_task(id=2, name="t2", success_rate=100.0))
    deltas = PerfService._compute_deltas([a, b])
    assert deltas["success_rate"] == [None, None]


@pytest.mark.asyncio
async def test_compare_requires_two_tasks():
    svc = _svc()
    with pytest.raises(PerfValidationError) as e:
        await svc.compare_tasks([1])
    assert "2-4" in str(e.value)


@pytest.mark.asyncio
async def test_compare_rejects_non_completed_task():
    svc = _svc()
    svc.repo.get_by_id = AsyncMock(
        return_value=_compare_task(id=1, status="running")
    )
    with pytest.raises(PerfValidationError) as e:
        await svc.compare_tasks([1, 2])
    assert "只有已完成的任务可对比" in str(e.value)


@pytest.mark.asyncio
async def test_compare_marks_strictly_comparable_when_fingerprints_match():
    svc = _svc()

    async def fake_get(tid):
        return _compare_task(id=tid, name=f"t{tid}", status="completed")

    svc.repo.get_by_id = AsyncMock(side_effect=fake_get)
    result = await svc.compare_tasks([1, 2])
    assert result.strictly_comparable is True
    assert result.diff_fields == []
    assert len(result.items) == 2


@pytest.mark.asyncio
async def test_compare_reports_diff_fields_when_fingerprints_differ():
    svc = _svc()
    tasks = {
        1: _compare_task(id=1, name="t1", status="completed", fingerprint="aaa"),
        2: _compare_task(
            id=2, name="t2", status="completed", fingerprint="bbb", parallel=100
        ),
    }
    svc.repo.get_by_id = AsyncMock(side_effect=lambda tid: tasks[tid])
    result = await svc.compare_tasks([1, 2])
    assert result.strictly_comparable is False
    assert "并发数" in result.diff_fields


# ============================================================
# random 数据集的 tokenizer 校验
# ============================================================

def _tok_payload(**overrides):
    base = _create_payload()          # dataset_type=random
    base.update(overrides)
    return base


def test_tokenizer_ok_when_task_specifies_it():
    data = PerfTaskCreate(**_tok_payload(tokenizer_path="Qwen/Qwen2.5-7B-Instruct"))
    model = mock_orm(name="m", provider="openai", model_config={})
    PerfService._assert_tokenizer_available(data, model)


def test_tokenizer_ok_when_model_has_hf_model_id():
    data = PerfTaskCreate(**_tok_payload())
    model = mock_orm(name="m", provider="openai", model_config={"hf_model_id": "Qwen/Qwen2.5-7B"})
    PerfService._assert_tokenizer_available(data, model)


def test_tokenizer_required_for_random_dataset():
    """没 tokenizer 也没 hf_model_id → 创建阶段就拒绝，别等子进程跑 7 秒才报错。"""
    data = PerfTaskCreate(**_tok_payload())
    model = mock_orm(name="m", provider="openai", model_config={})
    with pytest.raises(PerfValidationError) as e:
        PerfService._assert_tokenizer_available(data, model)
    assert "tokenizer" in str(e.value)
    assert "hf_model_id" in str(e.value)


def test_tokenizer_not_required_for_non_random_dataset():
    data = PerfTaskCreate(
        **_tok_payload(dataset_type="openqa", input_length=None, output_length=None)
    )
    model = mock_orm(name="m", provider="openai", model_config={})
    PerfService._assert_tokenizer_available(data, model)


def test_tokenizer_handles_none_model_config():
    data = PerfTaskCreate(**_tok_payload())
    model = mock_orm(name="m", provider="openai", model_config=None)
    with pytest.raises(PerfValidationError):
        PerfService._assert_tokenizer_available(data, model)


# ============================================================
# 经网关压测必须配置平台 API Key
# ============================================================

def test_gateway_mode_requires_api_key(monkeypatch):
    """没配 PERF_GATEWAY_API_KEY 时经网关压测会 401，
    EvalScope 只报 'Test connection failed'，所以创建时就拦。"""
    monkeypatch.setattr(settings, "perf_gateway_api_key", "")
    data = PerfTaskCreate(**_tok_payload(via_gateway=True))
    with pytest.raises(PerfValidationError) as e:
        PerfService._assert_gateway_key_available(data)
    assert "PERF_GATEWAY_API_KEY" in str(e.value)


def test_gateway_mode_ok_when_api_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "perf_gateway_api_key", "sk-test-123")
    data = PerfTaskCreate(**_tok_payload(via_gateway=True))
    PerfService._assert_gateway_key_available(data)


def test_direct_mode_does_not_require_gateway_key(monkeypatch):
    """直连模型不需要平台 Key。"""
    monkeypatch.setattr(settings, "perf_gateway_api_key", "")
    data = PerfTaskCreate(**_tok_payload(via_gateway=False))
    PerfService._assert_gateway_key_available(data)


# ============================================================
# 进度文件 / 子进程日志（Phase2 未验证假设 #3 的回归保护）
# ============================================================

def test_read_progress_finds_file_in_work_dir(tmp_path):
    (tmp_path / "progress.json").write_text(
        json.dumps({"percent": 42, "processed_count": 42, "total_count": 100}), encoding="utf-8"
    )
    data = engine._read_progress(str(tmp_path))
    assert data["percent"] == 42


def test_read_progress_finds_file_in_subdirectory(tmp_path):
    """EvalScope 某些版本把 progress.json 写在 {outputs_dir}/{task_name}/ 下。"""
    sub = tmp_path / "perf_task_7"
    sub.mkdir()
    (sub / "progress.json").write_text(
        json.dumps({"percent": 88, "processed_count": 88, "total_count": 100}), encoding="utf-8"
    )
    data = engine._read_progress(str(tmp_path))
    assert data["percent"] == 88


def test_read_progress_prefers_newest(tmp_path):
    """两处都有时取 mtime 最新的那个。"""
    import os
    import time

    sub = tmp_path / "perf_task_7"
    sub.mkdir()
    (sub / "progress.json").write_text(json.dumps({"percent": 10}), encoding="utf-8")
    time.sleep(0.01)
    (tmp_path / "progress.json").write_text(json.dumps({"percent": 90}), encoding="utf-8")
    assert engine._read_progress(str(tmp_path))["percent"] == 90
    os.utime(sub / "progress.json", (time.time() + 10, time.time() + 10))
    assert engine._read_progress(str(tmp_path))["percent"] == 10


def test_read_progress_returns_none_when_missing(tmp_path):
    assert engine._read_progress(str(tmp_path)) is None


def test_read_progress_handles_half_written_json(tmp_path):
    (tmp_path / "progress.json").write_text('{"percent": 4', encoding="utf-8")
    assert engine._read_progress(str(tmp_path)) is None


def test_read_file_tail_truncates(tmp_path):
    p = tmp_path / "engine.log"
    p.write_text("A" * 5000 + "TAIL", encoding="utf-8")
    tail = engine._read_file_tail(str(p), limit=10)
    assert tail == "AAAAAAATAIL"[-10:]
    assert len(tail) == 10


def test_read_file_tail_missing_file(tmp_path):
    assert engine._read_file_tail(str(tmp_path / "nope.log")) == ""


@pytest.mark.asyncio
async def test_get_engine_log_reports_missing(tmp_path):
    svc = _svc()
    monkeypatch_target = __import__("app.services.perf_engine", fromlist=["x"])
    orig = monkeypatch_target.task_work_dir
    monkeypatch_target.task_work_dir = lambda tid: str(tmp_path)
    try:
        out = await svc.get_engine_log(1)
        assert out["exists"] is False
        assert "tokenizer" in out["hint"]
    finally:
        monkeypatch_target.task_work_dir = orig


@pytest.mark.asyncio
async def test_get_engine_log_returns_tail(tmp_path):
    (tmp_path / "engine.log").write_text(
        "\n".join(f"line{i}" for i in range(1, 51)), encoding="utf-8"
    )
    svc = _svc()
    import app.services.perf_engine as pe

    orig = pe.task_work_dir
    pe.task_work_dir = lambda tid: str(tmp_path)
    try:
        out = await svc.get_engine_log(1, lines=5)
        assert out["exists"] is True
        assert out["content"].splitlines() == ["line46", "line47", "line48", "line49", "line50"]
    finally:
        pe.task_work_dir = orig


# ============================================================
# 可压测模型列表（前端下拉数据源）
# ============================================================

@pytest.mark.asyncio
async def test_list_testable_models_filters_third_party(monkeypatch):
    """仅当显式配置白名单时才过滤；默认不过滤（见 test_list_testable_models_returns_all_by_default）。"""
    monkeypatch.setattr(settings, "perf_testable_provider_prefix", "local-")
    svc = _svc()
    svc.model_repo.get_all = AsyncMock(
        return_value=[
            mock_orm(id=1, name="qwen-7b", provider="local-vllm", api_base_url="http://a/v1", model_config={}),
            mock_orm(id=2, name="gpt-4", provider="openai", api_base_url="https://api.openai.com/v1", model_config={}),
            mock_orm(id=3, name="ds", provider="deepseek", api_base_url="https://x/v1", model_config={}),
        ]
    )
    models = await svc.list_testable_models()
    assert [m["name"] for m in models] == ["qwen-7b"]


@pytest.mark.asyncio
async def test_list_testable_models_exposes_hf_model_id():
    svc = _svc()
    svc.model_repo.get_all = AsyncMock(
        return_value=[
            mock_orm(
                id=1,
                name="qwen-7b",
                provider="local-vllm",
                status="online",
                api_base_url="http://a/v1",
                model_config={"hf_model_id": "Qwen/Qwen2.5-7B-Instruct"},
            )
        ]
    )
    models = await svc.list_testable_models()
    assert models[0]["hf_model_id"] == "Qwen/Qwen2.5-7B-Instruct"


@pytest.mark.asyncio
async def test_list_testable_models_ignores_status():
    """status 非 online 也要能选 —— 否则新建模型（pending）永远选不到。"""
    svc = _svc()
    svc.model_repo.get_all = AsyncMock(
        return_value=[
            mock_orm(id=1, name="pending-model", provider="local-vllm", status="pending",
                     api_base_url="http://a/v1", model_config={}),
            mock_orm(id=2, name="offline-model", provider="local-vllm", status="offline",
                     api_base_url="http://b/v1", model_config={}),
        ]
    )
    models = await svc.list_testable_models()
    assert [m["name"] for m in models] == ["pending-model", "offline-model"]
    assert models[0]["status"] == "pending"


def test_testable_provider_no_restriction_by_default(monkeypatch):
    """默认（白名单留空）不限制 provider。"""
    monkeypatch.setattr(settings, "perf_testable_provider_prefix", "")
    assert PerfService._testable_prefixes() == []
    for provider in ("local-vllm", "openai", "ollama", "", None):
        assert PerfService.is_testable_provider(provider) is True


def test_testable_provider_accepts_comma_list(monkeypatch):
    monkeypatch.setattr(settings, "perf_testable_provider_prefix", "local-,vllm,ollama")
    assert PerfService.is_testable_provider("vllm") is True
    assert PerfService.is_testable_provider("ollama-prod") is True
    assert PerfService.is_testable_provider("local-vllm") is True
    assert PerfService.is_testable_provider("deepseek") is False


@pytest.mark.asyncio
async def test_list_testable_models_returns_all_by_default(monkeypatch):
    """默认把所有模型都列出来 —— 本地部署但 provider 是 openai 的模型也要可选。"""
    monkeypatch.setattr(settings, "perf_testable_provider_prefix", "")
    svc = _svc()
    svc.model_repo.get_all = AsyncMock(
        return_value=[
            mock_orm(id=1, name="/data/models/MiniMax-M3-AWQ-INT4", provider="openai",
                     status="online", api_base_url="http://10.51.13.7:8000/v1", model_config={}),
            mock_orm(id=2, name="Qwen3.8", provider="openai",
                     status="pending", api_base_url="http://10.51.13.7:8000/v1", model_config={}),
        ]
    )
    models = await svc.list_testable_models()
    assert [m["name"] for m in models] == ["/data/models/MiniMax-M3-AWQ-INT4", "Qwen3.8"]
