"""转发层与真实 httpx 的签名兼容性测试。

**为什么需要这个文件**

`tests/test_proxy_sse.py` 等测试把 httpx 的 `send()` / `post()` 全 mock 了，
mock 接受任意参数 —— 于是 `client.send(req, timeout=...)` 这种
「真实 httpx 签名不支持」的调用在单测里完全看不出来，
上线后直接 `TypeError: AsyncClient.send() got an unexpected keyword argument 'timeout'`。

这里改用 `httpx.MockTransport`：httpx 的真实实现参与调用链，
只是把网络层替换掉。签名错误会立刻抛 TypeError，且无需真实网络。
"""
from unittest.mock import AsyncMock

import httpx
import pytest

from tests.helpers import mock_orm

from app.services import proxy_service as psm
from app.services.proxy_service import ProxyService

SSE_BODY = (
    b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
    b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":4}}\n\n'
    b"data: [DONE]\n\n"
)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ============================================================
# open_stream：真实 send() 签名
# ============================================================

@pytest.mark.asyncio
async def test_open_stream_uses_real_send_signature(monkeypatch):
    """若 open_stream 给 send() 传了不支持的参数（如 timeout），此处会 TypeError。"""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["accept"] = request.headers.get("accept")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=SSE_BODY,
        )

    client = _client(handler)
    monkeypatch.setattr(psm, "get_http_client", lambda: client)

    svc = ProxyService(AsyncMock())
    model = mock_orm(api_base_url="http://upstream:8000/v1", api_key_encrypted="sk-up")
    resp = await svc.open_stream(model, {"model": "m", "messages": []})

    try:
        assert resp.status_code == 200
        payload = b"".join([chunk async for chunk in resp.aiter_bytes()])
        assert payload == SSE_BODY
        assert seen["url"] == "http://upstream:8000/v1/chat/completions"
        assert seen["auth"] == "Bearer sk-up"
        assert seen["accept"] == "text/event-stream"
    finally:
        await resp.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_open_stream_without_api_key_sends_no_auth_header(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=SSE_BODY
        )

    client = _client(handler)
    monkeypatch.setattr(psm, "get_http_client", lambda: client)

    svc = ProxyService(AsyncMock())
    model = mock_orm(api_base_url="http://local:8000/v1", api_key_encrypted=None)
    resp = await svc.open_stream(model, {"model": "m", "messages": []})
    try:
        assert captured["auth"] is None
    finally:
        await resp.aclose()
        await client.aclose()


# ============================================================
# forward：真实 post() 签名
# ============================================================

@pytest.mark.asyncio
async def test_forward_uses_real_post_signature(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = _client(handler)
    monkeypatch.setattr(psm, "get_http_client", lambda: client)

    svc = ProxyService(AsyncMock())
    model = mock_orm(api_base_url="https://api.example.com/v1", api_key_encrypted="sk-ext")

    try:
        resp = await svc.forward(model, {"model": "m", "messages": []})
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "ok"
        assert seen["url"] == "https://api.example.com/v1/chat/completions"
        assert seen["auth"] == "Bearer sk-ext"
    finally:
        await client.aclose()


# ============================================================
# 流式端到端：open_stream → _relay_sse_stream → usage 回填
# ============================================================

@pytest.mark.asyncio
async def test_streaming_end_to_end_relay_and_backfill(monkeypatch):
    """真实 httpx 响应流经 _relay_sse_stream，字节应原样透传并解析出 usage。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=SSE_BODY
        )

    client = _client(handler)
    monkeypatch.setattr(psm, "get_http_client", lambda: client)

    from app.api.v1 import proxy as proxy_mod

    svc = ProxyService(AsyncMock())
    model = mock_orm(api_base_url="http://up:8000/v1", api_key_encrypted=None)
    upstream = await svc.open_stream(model, {"model": "m", "messages": []})

    backfilled: dict = {}

    async def fake_backfill(log_id, usage, app_key_id=None):
        backfilled["log_id"] = log_id
        backfilled["usage"] = usage
        backfilled["app_key_id"] = app_key_id

    monkeypatch.setattr(proxy_mod, "_backfill_log_usage", fake_backfill)

    try:
        out = b"".join([c async for c in proxy_mod._relay_sse_stream(upstream, 42)])
        assert out == SSE_BODY           # 客户端收到的字节与上游一致
        assert backfilled["log_id"] == 42
        assert backfilled["usage"] == {"prompt_tokens": 3, "completion_tokens": 4}
    finally:
        await client.aclose()


# ============================================================
# 共享客户端不应被流式转发关闭
# ============================================================

@pytest.mark.asyncio
async def test_shared_client_not_closed_by_response(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=SSE_BODY
        )

    client = _client(handler)
    monkeypatch.setattr(psm, "get_http_client", lambda: client)

    svc = ProxyService(AsyncMock())
    model = mock_orm(api_base_url="http://up:8000/v1", api_key_encrypted=None)

    from app.api.v1 import proxy as proxy_mod

    upstream = await svc.open_stream(model, {"model": "m", "messages": []})
    monkeypatch.setattr(proxy_mod, "_backfill_log_usage", AsyncMock())
    _ = b"".join([c async for c in proxy_mod._relay_sse_stream(upstream, None)])

    assert client.is_closed is False, "流式结束后共享客户端被错误关闭了"
    await client.aclose()
