import hashlib
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from tests.helpers import mock_orm

from app.services.proxy_service import ProxyService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def proxy_service(mock_db):
    return ProxyService(mock_db)


# ============================================================
# Key 鉴权
# ============================================================

def _raw_key() -> str:
    return "sk-" + "a" * 48


def _key_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@pytest.mark.asyncio
async def test_authenticate_key_valid(proxy_service, mock_db):
    """有效 Key（active、未过期）应通过校验并刷新 last_used_at。"""
    raw = _raw_key()
    key = mock_orm(
        id=1,
        key_hash=_key_hash(raw),
        status="active",
        deleted_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    # mock execute 返回 key
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = key
    mock_db.execute = AsyncMock(return_value=result_mock)

    found = await proxy_service.authenticate_key(raw)
    assert found is not None
    assert found.id == 1
    assert key.last_used_at is not None  # 已刷新


@pytest.mark.asyncio
async def test_authenticate_key_missing(proxy_service, mock_db):
    """空 Key / 无 Key 应返回 None。"""
    assert await proxy_service.authenticate_key("") is None
    assert await proxy_service.authenticate_key(None) is None


@pytest.mark.asyncio
async def test_authenticate_key_invalid(proxy_service, mock_db):
    """未找到的 Key（哈希不匹配）应返回 None。"""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=result_mock)

    found = await proxy_service.authenticate_key(_raw_key())
    assert found is None


@pytest.mark.asyncio
async def test_authenticate_key_disabled(proxy_service, mock_db):
    """disabled 状态的 Key 应被拒绝。"""
    raw = _raw_key()
    key = mock_orm(id=1, key_hash=_key_hash(raw), status="disabled", deleted_at=None)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = key
    mock_db.execute = AsyncMock(return_value=result_mock)

    found = await proxy_service.authenticate_key(raw)
    assert found is None


@pytest.mark.asyncio
async def test_authenticate_key_expired(proxy_service, mock_db):
    """过期 Key 应自动置为 expired 并拒绝。"""
    raw = _raw_key()
    key = mock_orm(
        id=1,
        key_hash=_key_hash(raw),
        status="active",
        deleted_at=None,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = key
    mock_db.execute = AsyncMock(return_value=result_mock)

    found = await proxy_service.authenticate_key(raw)
    assert found is None
    assert key.status == "expired"  # 已被标记


# ============================================================
# 模型解析与权限
# ============================================================

@pytest.mark.asyncio
async def test_resolve_model_online(proxy_service, mock_db):
    """在线的模型应能解析到。"""
    model = mock_orm(id=1, name="local-qwen", status="online", deleted_at=None)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = model
    mock_db.execute = AsyncMock(return_value=result_mock)

    found = await proxy_service.resolve_model("local-qwen")
    assert found is not None
    assert found.id == 1


@pytest.mark.asyncio
async def test_resolve_model_not_found(proxy_service, mock_db):
    """不存在的模型应返回 None。"""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=result_mock)

    assert await proxy_service.resolve_model("no-such-model") is None


@pytest.mark.asyncio
async def test_resolve_model_empty_name(proxy_service):
    assert await proxy_service.resolve_model("") is None
    assert await proxy_service.resolve_model(None) is None


@pytest.mark.asyncio
async def test_key_can_access_unrestricted(proxy_service, mock_db):
    """Key 未绑定模型 = 全部放行。"""
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result_mock)

    assert await proxy_service.key_can_access_model(1, 99) is True


@pytest.mark.asyncio
async def test_key_can_access_restricted_allowed(proxy_service, mock_db):
    """绑定模型后：包含该模型 → 放行。"""
    perm = mock_orm(id=1, app_key_id=1, model_id=5)
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [perm]
    mock_db.execute = AsyncMock(return_value=result_mock)

    assert await proxy_service.key_can_access_model(1, 5) is True
    assert await proxy_service.key_can_access_model(1, 6) is False


# ============================================================
# 转发与记录
# ============================================================

@pytest.mark.asyncio
async def test_forward_local_model_no_key(proxy_service, mock_db):
    """本地无 Key 模型：转发时不携带 Authorization，URL 拼 /chat/completions。"""
    model = mock_orm(
        id=1,
        name="local-qwen",
        api_base_url="http://127.0.0.1:8001/v1",
        api_key_encrypted=None,
    )
    body = {"model": "local-qwen", "messages": [{"role": "user", "content": "hi"}]}

    with pytest.MonkeyPatch.context() as mp:
        captured = {}

        async def fake_post(self, url, json=None, headers=None, timeout=None, **kwargs):
            captured["url"] = url
            captured["headers"] = headers
            resp = MagicMock()
            resp.status_code = 200
            return resp

        mp.setattr("httpx.AsyncClient.post", fake_post)
        resp = await proxy_service.forward(model, body)

    assert captured["url"] == "http://127.0.0.1:8001/v1/chat/completions"
    assert "Authorization" not in (captured["headers"] or {})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_forward_remote_model_with_key(proxy_service, mock_db):
    """远程模型带 Key：转发时携带 Authorization。"""
    model = mock_orm(
        id=2,
        name="deepseek-v3",
        api_base_url="https://api.deepseek.com/v1",
        api_key_encrypted="sk-encrypted-key",
    )
    body = {"model": "deepseek-v3", "messages": []}

    with pytest.MonkeyPatch.context() as mp:
        captured = {}

        async def fake_post(self, url, json=None, headers=None, timeout=None, **kwargs):
            captured["headers"] = headers
            resp = MagicMock()
            resp.status_code = 200
            return resp

        mp.setattr("httpx.AsyncClient.post", fake_post)
        await proxy_service.forward(model, body)

    assert captured["headers"].get("Authorization") == "Bearer sk-encrypted-key"


@pytest.mark.asyncio
async def test_record_request(proxy_service, mock_db):
    """请求日志记录应正确汇总 token。"""
    await proxy_service.record_request(
        request_id="req_x", app_key_id=1, model_id=2,
        request_path="/v1/chat/completions",
        prompt_tokens=10, completion_tokens=5,
    )
    assert mock_db.add.called
