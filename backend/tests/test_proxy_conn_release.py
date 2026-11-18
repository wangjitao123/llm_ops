"""网关连接占用测试：等上游生成期间不得占住数据库连接。

**为什么需要这个文件**

API 侧连接池大小 = `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × uvicorn worker 数`
（默认 (20+30)×2 = 100）。如果每个请求从鉴权到返回全程持有连接，并发上限就被
锁死在这个数，超出部分只能排队，最后以
`QueuePool limit ... connection timed out` 500 收场 —— 而且这种问题在功能测试里
完全看不出来（只有并发压上来才炸）。

流式分支早已在返回 StreamingResponse 前 close（见 proxy.py）；
非流式分支原先漏了：`svc.forward()` 在 commit 之前 await，连接被占满整个生成周期。
这里用「假会话记录连接状态」把三个位置的行为钉死：
  1. 非流式：调用上游前必须归还连接；
  2. 非流式：生成结束后日志照常写库（在归还之后重新取连接）；
  3. 主备切换：重连备机前必须归还连接（选路查询已完成）。
"""
import json
from unittest.mock import MagicMock

import httpx
import pytest
from starlette.requests import Request

from app.api.v1 import proxy as proxy_mod
from tests.helpers import mock_orm


# ============================================================
# 测试替身
# ============================================================

class FakeSession:
    """最小 AsyncSession 替身：只用 checked_out 表示当前是否占着一条连接。"""

    def __init__(self):
        self.checked_out = False
        self.events: list[str] = []

    # --- 真实 Session 上端点/服务会用到的方法 ---
    def in_transaction(self) -> bool:
        return self.checked_out

    async def execute(self, *args, **kwargs):
        self.checked_out = True
        self.events.append("execute")
        return MagicMock()

    def add(self, obj):
        self.checked_out = True
        self.events.append("add")

    async def flush(self):
        self.checked_out = True
        self.events.append("flush")

    async def commit(self):
        self.events.append("commit")

    async def rollback(self):
        self.events.append("rollback")

    async def close(self):
        self.checked_out = False
        self.events.append("close")


class FakeUpstreamResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


_KEY = mock_orm(
    id=1, name="app-a", qps_limit=None, status="active",
    # 配额字段必须显式给值：mock_orm 是 MagicMock，未设置的属性会自动生成 mock，
    # 而配额校验会把它当"已配置的上限"去做 int() 比较。
    rpm_limit=None, rpd_limit=None, token_quota=None, token_used=0,
)
_MODEL = mock_orm(id=1, name="Qwen3.8", status="online", deleted_at=None)
_ALT_MODEL = mock_orm(id=2, name="Qwen3.8", status="online", deleted_at=None)


class FakeProxyService:
    """记录「调用上游那一刻是否占着连接」，其余行为照着真实实现模拟（含查库）。"""

    instances: list["FakeProxyService"] = []
    fail_first_forward: bool = False
    key = _KEY                      # 可按用例替换（验证配额拦截）

    def __init__(self, db, suppress_request_log: bool = False):
        self.db = db
        self.suppress_request_log = suppress_request_log
        self.forward_calls: list[dict] = []
        self.record_kwargs: list[dict] = []
        self.token_used_calls: list[dict] = []
        FakeProxyService.instances.append(self)

    async def authenticate_key(self, raw_key):
        await self.db.execute(None)          # 模拟一次鉴权查询 → 占住连接
        return type(self).key

    async def resolve_model(self, model_name):
        await self.db.execute(None)
        return _MODEL

    async def key_can_access_model(self, key_id, model_id):
        await self.db.execute(None)
        return True

    async def get_deployment_config(self, model_id):
        await self.db.execute(None)
        return None

    async def forward(self, model, body):
        self.forward_calls.append({"model_id": model.id, "checked_out": self.db.checked_out})
        if type(self).fail_first_forward and len(self.forward_calls) == 1:
            raise httpx.TimeoutException("upstream timed out")
        return FakeUpstreamResponse(
            {"choices": [{"message": {"content": "ok"}}],
             "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
        )

    async def open_stream(self, model, body):   # 非流式用例不会走到，留桩
        raise AssertionError("非流式用例不应调用 open_stream")

    async def record_request(self, **kwargs):
        self.record_kwargs.append(kwargs)
        self.db.add(None)                    # 真实实现是 db.add(log)
        await self.db.flush()
        return None

    async def add_token_used(self, key_id, tokens):
        """真实实现会 UPDATE app_key.token_used；这里只记录调用与占连接。"""
        self.token_used_calls.append({"key_id": key_id, "tokens": tokens})
        if tokens:
            await self.db.execute(None)


class FakeGatewayService:
    """alt_for_failover 非空时，带 exclude_model_id 的选路返回备机。"""

    alt_for_failover = None

    def __init__(self, db):
        self.db = db

    async def get_effective_qps_limits(self):
        return (5000, 100)

    async def route_model_for(self, path, model_name, exclude_model_id=None):
        await self.db.execute(None)          # 模拟一次路由查询 → 占住连接
        if exclude_model_id is not None and type(self).alt_for_failover is not None:
            return (1, "active_standby", type(self).alt_for_failover)
        return (None, None, None)


async def _allow_qps(**_kwargs):
    return (True, 0)


@pytest.fixture(autouse=True)
def _reset_fakes():
    FakeProxyService.instances.clear()
    FakeProxyService.fail_first_forward = False
    FakeProxyService.key = _KEY
    FakeGatewayService.alt_for_failover = None
    yield


def _request(payload: dict) -> Request:
    raw = json.dumps(payload).encode()
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "root_path": "",
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
        "headers": [
            (b"authorization", b"Bearer sk-test"),
            (b"content-type", b"application/json"),
        ],
    }
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(scope, receive)


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(proxy_mod, "ProxyService", FakeProxyService)
    monkeypatch.setattr(proxy_mod, "GatewayService", FakeGatewayService)
    monkeypatch.setattr(proxy_mod, "check_qps", _allow_qps)


_BODY = {"model": "Qwen3.8", "messages": [{"role": "user", "content": "hi"}]}


# ============================================================
# 用例
# ============================================================

@pytest.mark.asyncio
async def test_non_stream_releases_conn_before_upstream(patched):
    """非流式：调用上游那一刻必须已经归还连接（鉴权/路由查询早已完成）。"""
    db = FakeSession()
    resp = await proxy_mod.chat_completions(_request(_BODY), db=db)

    assert resp.status_code == 200
    svc = FakeProxyService.instances[-1]
    assert svc.forward_calls, "未调用上游"
    assert svc.forward_calls[0]["checked_out"] is False, \
        "非流式请求在等上游生成时仍占着数据库连接"


@pytest.mark.asyncio
async def test_non_stream_log_still_written_after_release(patched):
    """非流式：归还连接不影响记账，日志在生成结束后重新取连接写库。"""
    db = FakeSession()
    await proxy_mod.chat_completions(_request(_BODY), db=db)

    svc = FakeProxyService.instances[-1]
    assert len(svc.record_kwargs) == 1, "日志没有正常写入"
    assert svc.record_kwargs[0]["prompt_tokens"] == 3
    assert svc.record_kwargs[0]["completion_tokens"] == 4

    # 先 close（归还）→ 后 add（重新取连接写日志）
    assert "close" in db.events
    assert "add" in db.events
    assert db.events.index("close") < db.events.index("add")

    # 累计 Key 已用 token（3+4），供 token_quota 判断
    assert svc.token_used_calls == [{"key_id": 1, "tokens": 7}]


@pytest.mark.asyncio
async def test_failover_releases_conn_before_reconnect(patched):
    """主备切换：选路查完后归还连接，重连备机期间不得占着连接。"""
    FakeProxyService.fail_first_forward = True
    FakeGatewayService.alt_for_failover = _ALT_MODEL
    db = FakeSession()

    resp = await proxy_mod.chat_completions(_request(_BODY), db=db)

    assert resp.status_code == 200, "备机重连后应正常返回"
    svc = FakeProxyService.instances[-1]
    assert len(svc.forward_calls) == 2, "应先失败再切备机"
    assert svc.forward_calls[0]["checked_out"] is False
    assert svc.forward_calls[1]["model_id"] == _ALT_MODEL.id, "未切到备机"
    assert svc.forward_calls[1]["checked_out"] is False, \
        "切换备机后重新占住了数据库连接"


# ============================================================
# 配额拦截（网关接线）
# ============================================================

@pytest.mark.asyncio
async def test_token_quota_exhausted_rejected_before_upstream(patched):
    """token 配额用尽：429 insufficient_quota，且不转发上游、不写日志。"""
    FakeProxyService.key = mock_orm(
        id=1, name="app-a", qps_limit=None, status="active",
        rpm_limit=None, rpd_limit=None, token_quota=100, token_used=100,
    )
    db = FakeSession()
    resp = await proxy_mod.chat_completions(_request(_BODY), db=db)

    assert resp.status_code == 429
    assert json.loads(resp.body)["error"]["type"] == "insufficient_quota"

    svc = FakeProxyService.instances[-1]
    assert svc.forward_calls == [], "配额已用尽却仍把请求转发给了上游"
    assert svc.record_kwargs == [], "被配额拒绝的请求不应计入用量日志"


@pytest.mark.asyncio
async def test_rpm_quota_rejected_with_retry_after(patched, monkeypatch):
    """分钟/每日配额超限：429 rate_limit_error，并带 Retry-After。"""
    async def deny(**_kwargs):
        return (False, 42)

    monkeypatch.setattr(proxy_mod, "check_key_windows", deny)
    db = FakeSession()
    resp = await proxy_mod.chat_completions(_request(_BODY), db=db)

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "42"
    assert json.loads(resp.body)["error"]["type"] == "rate_limit_error"
    assert FakeProxyService.instances[-1].forward_calls == []