"""网关 verify-key 端点的 API 级测试（对 service 层打桩，不连真实 DB）。"""
import hashlib
from datetime import datetime, timezone, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from tests.helpers import mock_orm


def _mk_key(id_, raw):
    return mock_orm(
        id=id_,
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        key_prefix=raw[:10],
        name=f"key-{id_}",
        status="active",
        deleted_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        token_quota=None,
        token_used=0,
    )


@pytest.fixture
def client():
    # 避免 app lifespan 里的 redis ping，直接构造 app 但跳过 lifespan 用 TestClient(app, raise_server_exceptions=False)
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _patch_auth(mocker_key):
    """把 ProxyService.authenticate_key 与 list_key_allowed_model_ids 打桩。"""

    def _patch(db_mock=None):
        return patch.multiple(
            "app.services.proxy_service.ProxyService",
            authenticate_key=AsyncMock(return_value=mocker_key),
            list_key_allowed_model_ids=AsyncMock(return_value=None),
        )

    return _patch


def test_verify_key_valid_returns_key_info(client):
    raw = "sk-validvalidvalidvalidvalidvalidvalidvalid"
    key = _mk_key(1, raw)

    with patch("app.services.proxy_service.ProxyService.authenticate_key", new=AsyncMock(return_value=key)), \
         patch("app.services.proxy_service.ProxyService.list_key_allowed_model_ids", new=AsyncMock(return_value=None)):
        resp = client.post("/api/v1/gateway/verify-key", json={"key": raw})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["key_id"] == 1
    assert data["allowed_model_ids"] is None


def test_verify_key_invalid_returns_401(client):
    with patch("app.services.proxy_service.ProxyService.authenticate_key", new=AsyncMock(return_value=None)):
        resp = client.post("/api/v1/gateway/verify-key", json={"key": "sk-bad"})

    assert resp.status_code == 200  # 统一响应壳
    body = resp.json()
    assert body["code"] == 401
    assert body["data"] is None


def test_verify_key_missing_field_returns_422(client):
    resp = client.post("/api/v1/gateway/verify-key", json={})
    assert resp.status_code == 422
