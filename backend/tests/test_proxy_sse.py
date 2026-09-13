"""SSE 流式请求 Token 统计相关测试：usage 解析、include_usage 注入、透传回填。"""
import pytest
from unittest.mock import MagicMock

from app.api.v1 import proxy as proxy_mod
from app.services.proxy_service import ProxyService


# ============================================================
# 纯函数：SSE usage 解析
# ============================================================

def test_parse_usage_payload_valid():
    payload = '{"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 34}}'
    assert proxy_mod._parse_usage_payload(payload) == {"prompt_tokens": 12, "completion_tokens": 34}


def test_parse_usage_payload_no_usage():
    payload = '{"choices": [{"delta": {"content": "hi"}}]}'
    assert proxy_mod._parse_usage_payload(payload) is None


def test_parse_usage_payload_done_and_garbage():
    assert proxy_mod._parse_usage_payload("[DONE]") is None
    assert proxy_mod._parse_usage_payload("") is None
    assert proxy_mod._parse_usage_payload("not-json{{{") is None
    assert proxy_mod._parse_usage_payload('{"usage": null}') is None


# ============================================================
# 纯函数：include_usage 注入
# ============================================================

def test_ensure_include_usage_injects_when_missing():
    body = {"model": "m", "stream": True, "messages": []}
    out, changed = proxy_mod._ensure_include_usage(body)
    assert changed is True
    assert out["stream_options"] == {"include_usage": True}
    # 不改动原 body
    assert "stream_options" not in body


def test_ensure_include_usage_keeps_existing():
    body = {"model": "m", "stream": True, "stream_options": {"include_usage": True}}
    out, changed = proxy_mod._ensure_include_usage(body)
    assert changed is False
    assert out is body


def test_ensure_include_usage_merges_other_options():
    body = {"model": "m", "stream": True, "stream_options": {"chat_template_kwargs": {"x": 1}}}
    out, changed = proxy_mod._ensure_include_usage(body)
    assert changed is True
    assert out["stream_options"] == {"chat_template_kwargs": {"x": 1}, "include_usage": True}


def test_ensure_include_usage_skips_non_stream_and_non_dict():
    body = {"model": "m", "messages": []}
    out, changed = proxy_mod._ensure_include_usage(body)
    assert changed is False and out is body
    out2, changed2 = proxy_mod._ensure_include_usage(None)
    assert changed2 is False and out2 is None


# ============================================================
# SSE 透传 + 回填
# ============================================================

class FakeUpstream:
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks
        self.closed = False

    def aiter_bytes(self):
        async def _it():
            for c in self.chunks:
                yield c
        return _it()

    async def aclose(self):
        self.closed = True


class FakeClient:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class FakeSession:
    """记录 execute / commit 的假会话，供 _backfill_log_usage 使用。"""

    def __init__(self):
        self.executed = []
        self.committed = False

    async def execute(self, stmt):
        self.executed.append(stmt)
        return MagicMock()

    async def commit(self):
        self.committed = True


class _SessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_relay_sse_passthrough_and_backfill(monkeypatch):
    """正常流：字节原样透传 + 流结束后用 usage 回填日志。"""
    sse = (
        b'data: {"choices":[{"delta":{"content":"hi"},"index":0}]}\n\n'
        b'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":34}}\n\n'
        b"data: [DONE]\n\n"
    )
    upstream = FakeUpstream([sse])
    client = FakeClient()
    session = FakeSession()
    monkeypatch.setattr(proxy_mod, "async_session", lambda: _SessionCtx(session))

    gen = proxy_mod._relay_sse_stream(upstream, client, log_id=7)
    out = b"".join([c async for c in gen])

    assert out == sse  # 客户端收到的字节与上游完全一致
    assert upstream.closed is True
    assert client.closed is True
    assert session.committed is True
    # 回填 UPDATE 语句的绑定参数应含 id=7 与 usage 数值
    values = []
    for stmt in session.executed:
        values.extend(stmt.compile().params.values())
    assert 7 in values and 12 in values and 34 in values and 46 in values  # 46 = 12+34


@pytest.mark.asyncio
async def test_relay_sse_no_usage_no_backfill(monkeypatch):
    """流里没有 usage（未注入生效的上游）：只透传，不产生回填更新。"""
    sse = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n' + b"data: [DONE]\n\n"
    upstream = FakeUpstream([sse])
    client = FakeClient()
    session = FakeSession()
    monkeypatch.setattr(proxy_mod, "async_session", lambda: _SessionCtx(session))

    out = b"".join([c async for c in proxy_mod._relay_sse_stream(upstream, client, log_id=7)])

    assert out == sse
    assert session.executed == []
    assert session.committed is False


@pytest.mark.asyncio
async def test_relay_sse_chunk_boundaries(monkeypatch):
    """usage 事件被拆成多个 chunk 也能拼出来（缓冲跨块）。"""
    sse = b'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":6}}\n\ndata: [DONE]\n\n'
    # 拆得很碎，每次 1 字节
    upstream = FakeUpstream([bytes([b]) for b in sse])
    client = FakeClient()
    session = FakeSession()
    monkeypatch.setattr(proxy_mod, "async_session", lambda: _SessionCtx(session))

    out = b"".join([c async for c in proxy_mod._relay_sse_stream(upstream, client, log_id=3)])

    assert out == sse
    assert session.committed is True
    values = []
    for stmt in session.executed:
        values.extend(stmt.compile().params.values())
    assert 3 in values and 5 in values and 6 in values


# ============================================================
# record_request 返回日志对象（流式回填需要 log.id）
# ============================================================

@pytest.mark.asyncio
async def test_record_request_returns_log():
    from unittest.mock import AsyncMock, MagicMock
    db = MagicMock()
    db.flush = AsyncMock()  # flush 是异步的；add 保持同步 mock，避免无谓告警
    svc = ProxyService(db)

    log = await svc.record_request(
        request_id="req_x", app_key_id=1, model_id=2,
        request_path="/v1/chat/completions",
        prompt_tokens=10, completion_tokens=5,
    )

    assert log is not None
    assert log.total_tokens == 15
    assert log.prompt_tokens == 10
    db.add.assert_called_once()
