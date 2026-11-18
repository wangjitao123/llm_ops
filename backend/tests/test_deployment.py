"""模型部署模块测试：纯逻辑（可单测）+ 服务层关键分支。"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from tests.helpers import mock_orm

from app.api.v1 import proxy as proxy_mod
from app.services import docker_service as ds
from app.services import gpu_service as gs
from app.services.deployment_service import DeploymentService, normalize_endpoint
from app.tasks import deployment_tasks as dt


# ============================================================
# Docker 纯逻辑
# ============================================================

def test_build_container_name_is_stable_and_unique_by_port():
    name = ds.build_container_name(12, "vLLM", 31100)
    assert name == "dpl-12-vllm-31100"
    # 同部署不同端口 → 名字不同（避免重复部署撞名）
    assert ds.build_container_name(12, "vllm", 31101) != name


def test_allocate_port_skips_used_ports():
    port = ds.allocate_port({31100, 31101}, start=31100, end=31105)
    assert port == 31102


def test_allocate_port_raises_when_range_exhausted():
    with pytest.raises(ds.DeployError) as exc:
        ds.allocate_port({31100, 31101}, start=31100, end=31101)
    assert "耗尽" in str(exc.value)


def test_build_vllm_command_minimal():
    cmd = ds.build_vllm_command(
        model_ref="/models/qwen-7b-gptq",
        served_model_name="qwen-7b-gptq",
        api_key=None,
        max_model_len=4096,
    )
    assert cmd[:2] == ["--model", "/models/qwen-7b-gptq"]
    assert "--served-model-name" in cmd
    assert "--max-model-len" in cmd
    assert "--tensor-parallel-size" not in cmd
    assert "--api-key" not in cmd


def test_build_vllm_command_with_tp_and_api_key():
    cmd = ds.build_vllm_command(
        model_ref="Qwen/Qwen2.5-7B-Instruct",
        served_model_name="qwen-7b",
        api_key="sk-dpl-abc",
        max_model_len=8192,
        tensor_parallel_size=2,
        port=8000,
    )
    assert cmd[cmd.index("--tensor-parallel-size") + 1] == "2"
    assert cmd[cmd.index("--api-key") + 1] == "sk-dpl-abc"
    assert cmd[cmd.index("--port") + 1] == "8000"


def test_engine_image_known_and_unknown():
    assert ds.engine_image("vllm")
    with pytest.raises(ds.DeployError):
        ds.engine_image("nonsense-engine")


def test_container_and_host_endpoint_shapes():
    assert ds.container_endpoint("dpl-1-vllm-31100").endswith("/v1")
    assert "dpl-1-vllm-31100" in ds.container_endpoint("dpl-1-vllm-31100")
    assert ds.host_endpoint("10.0.0.1", 31100) == "http://10.0.0.1:31100/v1"


# ============================================================
# 端点归一化（防止网关拼出 .../chat/completions/chat/completions）
# ============================================================

def test_normalize_endpoint_strips_chat_completions():
    assert (
        normalize_endpoint("http://10.51.13.7:31000/v1/chat/completions")
        == "http://10.51.13.7:31000/v1"
    )


def test_normalize_endpoint_strips_trailing_slash():
    assert (
        normalize_endpoint("http://10.51.13.7:31000/v1/")
        == "http://10.51.13.7:31000/v1"
    )


def test_normalize_endpoint_keeps_plain_base():
    assert (
        normalize_endpoint("http://10.51.13.7:31000/v1")
        == "http://10.51.13.7:31000/v1"
    )


def test_normalize_endpoint_handles_empty():
    assert normalize_endpoint("") == ""
    assert normalize_endpoint(None) == ""


# ============================================================
# GPU 采集
# ============================================================

def test_parse_nvidia_smi_csv_ok():
    text = "0, 46068, 1234, 44834\n1, 46068, 0, 46068\n"
    gpus = gs.parse_nvidia_smi_csv(text)
    assert len(gpus) == 2
    assert gpus[0]["gpu_id"] == 0
    assert gpus[0]["memory_total_gb"] == pytest.approx(44.99, abs=0.01)
    assert gpus[1]["memory_used_gb"] == 0.0


def test_parse_nvidia_smi_csv_skips_bad_lines():
    text = "garbage line\n0, [N/A], 1, 2\n1, 46068, 10, 46058\n\n"
    gpus = gs.parse_nvidia_smi_csv(text)
    assert len(gpus) == 1
    assert gpus[0]["gpu_id"] == 1


def test_parse_nvidia_smi_csv_empty():
    assert gs.parse_nvidia_smi_csv("") == []
    assert gs.parse_nvidia_smi_csv(None) == []


def test_to_topology_attaches_deployment_names():
    raw = [{"gpu_id": 0, "memory_total_gb": 45.0, "memory_used_gb": 13.4, "memory_free_gb": 31.6}]
    result = gs.to_topology(raw, {0: ["qwen-7b"]})
    assert result[0].gpu_id == 0
    assert result[0].deployments == ["qwen-7b"]


def test_to_topology_handles_missing_fields():
    result = gs.to_topology([{"gpu_id": 2}], None)
    assert result[0].memory_used_gb == 0.0
    assert result[0].deployments == []


# ============================================================
# 部署任务纯逻辑
# ============================================================

def test_generate_model_api_key_has_prefix():
    key = dt.generate_model_api_key()
    assert key.startswith("sk-dpl-")
    assert len(key) > 20


def test_build_model_payload_shape():
    payload = dt.build_model_payload(
        name="qwen-7b-gptq",
        endpoint_url="http://dpl-1-vllm-31100:8000/v1",
        api_key="sk-dpl-x",
        qps_limit=64,
        hf_model_id="Qwen/Qwen2.5-7B-Instruct",
        engine="vllm",
        operator="alice",
    )
    assert payload["name"] == "qwen-7b-gptq"
    assert payload["provider"] == "local-vllm"
    assert payload["status"] == "online"
    assert payload["qps_limit"] == 64
    assert payload["health_check_url"].endswith("/models")
    assert payload["model_config"]["hf_model_id"] == "Qwen/Qwen2.5-7B-Instruct"
    assert payload["created_by"] == "alice"
    assert payload["updated_by"] == "alice"


def test_resolve_model_ref_uses_mounted_path():
    assert dt.resolve_model_ref("/models/qwen-7b-gptq", None) == "/models/qwen-7b-gptq"


def test_resolve_model_ref_joins_relative_path():
    assert dt.resolve_model_ref("qwen-7b-gptq", None) == "/models/qwen-7b-gptq"


def test_resolve_model_ref_falls_back_to_hf_id():
    assert dt.resolve_model_ref(None, "Qwen/Qwen2.5-7B-Instruct") == "Qwen/Qwen2.5-7B-Instruct"


def test_resolve_model_ref_requires_a_source():
    with pytest.raises(ds.DeployError):
        dt.resolve_model_ref(None, None)


def test_gpus_for_deployment_prefers_explicit_ids():
    assert dt.gpus_for_deployment(mock_orm(gpu_ids=[3, 4], gpu_count=2)) == [3, 4]


def test_gpus_for_deployment_defaults_to_first_n():
    assert dt.gpus_for_deployment(mock_orm(gpu_ids=None, gpu_count=2)) == [0, 1]


# ============================================================
# 网关注入部署配置
# ============================================================

def _deploy_cfg(**overrides):
    base = dict(
        system_prompt=None,
        tools_json=None,
        web_search_enabled=False,
        temperature=None,
        top_p=None,
        max_tokens=None,
        frequency_penalty=None,
    )
    base.update(overrides)
    return mock_orm(**base)


def test_apply_config_injects_system_prompt_when_absent():
    body = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    out = proxy_mod._apply_deployment_config(body, _deploy_cfg(system_prompt="你是助手"))
    assert out["messages"][0] == {"role": "system", "content": "你是助手"}
    assert out["messages"][1]["content"] == "hi"
    # 不改动原对象
    assert len(body["messages"]) == 1


def test_apply_config_keeps_caller_system_prompt():
    body = {
        "messages": [
            {"role": "system", "content": "调用方自己的"},
            {"role": "user", "content": "hi"},
        ]
    }
    out = proxy_mod._apply_deployment_config(body, _deploy_cfg(system_prompt="部署默认"))
    assert out["messages"][0]["content"] == "调用方自己的"
    assert len(out["messages"]) == 2


def test_apply_config_injects_tools_when_absent():
    tools = [{"type": "function", "function": {"name": "get_weather"}}]
    out = proxy_mod._apply_deployment_config({"messages": []}, _deploy_cfg(tools_json=tools))
    assert out["tools"] == tools
    assert out["tool_choice"] == "auto"


def test_apply_config_does_not_override_caller_tools():
    caller_tools = [{"type": "function", "function": {"name": "mine"}}]
    out = proxy_mod._apply_deployment_config(
        {"tools": caller_tools},
        _deploy_cfg(tools_json=[{"type": "function", "function": {"name": "theirs"}}]),
    )
    assert out["tools"] == caller_tools


def test_apply_config_fills_missing_sampling_params_only():
    body = {"temperature": 1.1}
    out = proxy_mod._apply_deployment_config(
        body,
        _deploy_cfg(temperature=0.2, top_p=0.9, max_tokens=512, frequency_penalty=0.1),
    )
    assert out["temperature"] == 1.1          # 调用方显式值优先
    assert out["top_p"] == 0.9
    assert out["max_tokens"] == 512
    assert out["frequency_penalty"] == 0.1


def test_apply_config_web_search_adds_tool_once():
    cfg = _deploy_cfg(web_search_enabled=True)
    out = proxy_mod._apply_deployment_config({"messages": []}, cfg)
    names = [t["function"]["name"] for t in out["tools"]]
    assert names == ["web_search"]
    assert out["tool_choice"] == "auto"

    # 再注入一次不应重复（已有同名工具时跳过）
    out2 = proxy_mod._apply_deployment_config({"tools": out["tools"]}, cfg)
    names2 = [t["function"]["name"] for t in out2["tools"]]
    assert names2 == ["web_search"]


def test_apply_config_web_search_appends_to_existing_tools():
    existing = [{"type": "function", "function": {"name": "get_weather"}}]
    out = proxy_mod._apply_deployment_config(
        {"tools": existing}, _deploy_cfg(web_search_enabled=True)
    )
    names = [t["function"]["name"] for t in out["tools"]]
    assert names == ["get_weather", "web_search"]


def test_apply_config_with_none_deploy_is_noop():
    body = {"messages": []}
    assert proxy_mod._apply_deployment_config(body, None) is body


# ============================================================
# DeploymentService 关键分支
# ============================================================

def _full_deploy(**overrides):
    """构造字段齐全、类型正确的部署 mock（足以通过 DeploymentResponse 校验）。"""
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        name="qwen-7b",
        deploy_type="managed",
        status="running",
        base_model_id=None,
        hf_model_id="Qwen/Qwen2.5-7B-Instruct",
        model_path=None,
        endpoint_url="http://dpl-1-vllm-31100:8000/v1",
        container_name="dpl-1-vllm-31100",
        host_port=31100,
        registered_model_id=None,
        engine="vllm",
        gpu_ids=None,
        gpu_count=1,
        gpu_memory_gb=13.4,
        max_concurrency=32,
        max_input_tokens=4096,
        system_prompt=None,
        temperature=0.7,
        top_p=0.9,
        max_tokens=4096,
        frequency_penalty=0.0,
        tools_json=None,
        web_search_enabled=False,
        web_search_config=None,
        env_vars=None,
        auto_register=True,
        health_check_enabled=True,
        error_message=None,
        created_by="alice",
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return mock_orm(**base)


def _service():
    service = DeploymentService(AsyncMock())
    service.repo = AsyncMock()
    service.model_repo = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_stop_rejects_non_managed_deployment():
    service = _service()
    service.repo.get_by_id = AsyncMock(return_value=_full_deploy(deploy_type="conda"))
    with pytest.raises(ValueError) as exc:
        await service.stop_deployment(1)
    assert "不支持平台" in str(exc.value)


@pytest.mark.asyncio
async def test_stop_dispatches_container_stop():
    service = _service()
    service.repo.get_by_id = AsyncMock(return_value=_full_deploy())
    service.repo.update = AsyncMock(return_value=_full_deploy(status="stopped"))

    stopped = []
    monkeypatch_target = DeploymentService._dispatch_stop
    DeploymentService._dispatch_stop = staticmethod(lambda name: stopped.append(name))
    try:
        result = await service.stop_deployment(1)
    finally:
        DeploymentService._dispatch_stop = monkeypatch_target

    assert result["status"] == "stopped"
    assert stopped == ["dpl-1-vllm-31100"]


@pytest.mark.asyncio
async def test_delete_deregisters_model_and_removes_container(monkeypatch):
    service = _service()
    service.repo.get_by_id = AsyncMock(
        return_value=_full_deploy(registered_model_id=9)
    )
    service.repo.delete = AsyncMock(return_value=True)

    removed = []
    monkeypatch.setattr(
        DeploymentService, "_dispatch_remove", staticmethod(lambda name: removed.append(name))
    )

    ok = await service.delete_deployment(1)

    assert ok is True
    service.model_repo.delete.assert_awaited_once_with(9)
    assert removed == ["dpl-1-vllm-31100"]


@pytest.mark.asyncio
async def test_start_rejects_when_not_stopped():
    service = _service()
    service.repo.get_by_id = AsyncMock(return_value=_full_deploy(status="running"))
    with pytest.raises(ValueError):
        await service.start_deployment(1)


@pytest.mark.asyncio
async def test_gpu_topology_returns_unavailable_when_no_gpu(monkeypatch):
    """无 GPU 且无缓存时，应返回可用性说明而不是抛异常。"""
    service = _service()
    service.db = AsyncMock()
    service.db.execute = AsyncMock(return_value=mock_orm(scalars=lambda: mock_orm(all=lambda: [])))

    async def no_cache():
        return None

    monkeypatch.setattr(gs, "read_snapshot", no_cache)
    monkeypatch.setattr(gs, "collect_local", lambda: (False, "none", "无 GPU", []))

    payload = await service.get_gpu_topology()
    assert payload["available"] is False
    assert payload["gpus"] == []
    assert "无 GPU" in (payload["error"] or "")


@pytest.mark.asyncio
async def test_gpu_topology_uses_cache_when_present(monkeypatch):
    service = _service()
    service.db = AsyncMock()
    service.db.execute = AsyncMock(return_value=mock_orm(scalars=lambda: mock_orm(all=lambda: [])))

    async def cached():
        return {
            "available": True,
            "source": "nvidia-smi",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "gpus": [{"gpu_id": 0, "memory_total_gb": 45.0, "memory_used_gb": 13.4, "memory_free_gb": 31.6}],
        }

    monkeypatch.setattr(gs, "read_snapshot", cached)

    payload = await service.get_gpu_topology()
    assert payload["available"] is True
    assert payload["source"] == "cache(nvidia-smi)"
    assert payload["gpus"][0]["memory_used_gb"] == 13.4
