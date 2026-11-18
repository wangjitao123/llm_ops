"""OpenAI 兼容统一入口（供外部应用调用平台模型）。

这就是用户诉求的落地：
  应用带平台 Key（Authorization: Bearer sk-xxx）+ OpenAI 格式请求体
  → POST {平台地址}/v1/chat/completions
  → 平台校验 Key → 解析模型 → 转发本地模型（无 Key）→ 返回 OpenAI 格式响应

高并发要点（详见 app/core/database.py、app/core/http.py）：
  * 流式请求在开始 SSE 转发前主动归还数据库连接（长时间占连接会打满连接池）；
  * 非流式请求同样在等上游生成前归还连接（否则并发上限 = 连接池大小）；
  * 主备失败切换在重连备机前也归还连接（选路查询已完成）；
  * 到上游模型复用全局共享 httpx 客户端（keep-alive），流结束只关 response。
"""
import json
import time
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, async_session
from app.models.key import AppKey
from app.models.token import ApiRequestLog
from app.services.gateway_service import GatewayService
from app.services.proxy_service import ProxyService
from app.services.rate_limiter import check_key_windows, check_qps, check_token_quota

router = APIRouter()


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


# 压测流量标记头（由 perf-worker 强制注入，见 ADR-004 / M04）
PERF_TEST_HEADER = "x-perf-test"
_PERF_TEST_TRUTHY = ("1", "true")


def _is_perf_test_request(headers) -> bool:
    """是否为压测流量。

    仅精确匹配 `1` / `true`（大小写、首尾空白不敏感），避免任意值绕过统计。

    安全边界（见 docs/需求理解/v4-模型压测/M04-流量标记与隔离）：
      该标记**只影响请求日志写入**，鉴权、限流、路由全部照常执行 ——
      所以伪造此头不会获得额外配额，只是自己的请求不进报表。
    """
    if not headers:
        return False
    raw = headers.get(PERF_TEST_HEADER)
    if raw is None:
        # Starlette Headers 本身大小写不敏感；但普通 dict 可能不是
        try:
            raw = headers.get(PERF_TEST_HEADER.title())
        except Exception:  # noqa: BLE001
            raw = None
    if raw is None:
        return False
    return str(raw).strip().lower() in _PERF_TEST_TRUTHY


def _usage_from_body(body: dict) -> dict:
    """从请求/响应体中尽量提取 token 用量；拿不到就按 0 计。"""
    usage = (body or {}).get("usage") or {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
    }


def _ensure_include_usage(body: dict) -> tuple[dict, bool]:
    """流式请求缺省注入 stream_options.include_usage=true。

    OpenAI 兼容上游（OpenAI/DeepSeek/vLLM 等）只有在收到 include_usage 时才在
    SSE 末尾返回 usage；不注入则流式请求的 token 用量永远拿不到。
    返回 (转发请求体, 是否注入了新字段)。
    """
    if not isinstance(body, dict) or not body.get("stream"):
        return body, False
    so = body.get("stream_options")
    if isinstance(so, dict) and so.get("include_usage"):
        return body, False
    merged = dict(so) if isinstance(so, dict) else {}
    merged["include_usage"] = True
    return {**body, "stream_options": merged}, True


# web_search 启用时注入给模型的工具定义。
# 注意：平台只负责"告诉模型有这个工具"，真正的搜索执行由调用方应用完成
# （符合 OpenAI function calling 语义：工具由客户端执行）。
WEB_SEARCH_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for up-to-date information beyond the model's training data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"],
        },
    },
}

# 部署配置里可下发给上游的采样参数（请求显式给出时不覆盖）
_SAMPLING_FIELDS = ("temperature", "top_p", "max_tokens", "frequency_penalty")


def _apply_deployment_config(body: dict, deploy) -> dict:
    """把部署级配置注入请求体。

    优先级：请求里显式给的值 > 部署配置 > 上游默认。
    只做"补齐"，绝不覆盖调用方明确传入的参数。

    注入内容：
      * system_prompt —— 请求未带 system 消息时前置一条
      * tools_json    —— 请求未带 tools 时附加
      * web_search    —— 启用时补一个 web_search 工具定义（若尚未声明同名工具）
      * 采样参数      —— 请求未指定时补部署默认值
    """
    if not isinstance(body, dict) or deploy is None:
        return body

    out = dict(body)

    # ---- system prompt ----
    system_prompt = getattr(deploy, "system_prompt", None)
    if system_prompt:
        messages = out.get("messages")
        if isinstance(messages, list):
            has_system = any(
                isinstance(m, dict) and m.get("role") == "system" for m in messages
            )
            if not has_system:
                out["messages"] = [{"role": "system", "content": system_prompt}] + messages

    # ---- tools ----
    tools = getattr(deploy, "tools_json", None)
    if tools and not out.get("tools"):
        out["tools"] = list(tools)
        out.setdefault("tool_choice", "auto")

    # ---- web search ----
    if getattr(deploy, "web_search_enabled", False):
        current = out.get("tools")
        if not isinstance(current, list):
            current = []
        declared = {
            (t or {}).get("function", {}).get("name")
            for t in current
            if isinstance(t, dict)
        }
        if "web_search" not in declared:
            out["tools"] = current + [WEB_SEARCH_TOOL]
        out.setdefault("tool_choice", "auto")

    # ---- 采样参数 ----
    for field in _SAMPLING_FIELDS:
        if out.get(field) is None:
            value = getattr(deploy, field, None)
            if value is not None:
                out[field] = value

    return out


def _parse_usage_payload(payload: str) -> Optional[dict]:
    """从一条 SSE data 载荷中解析 usage；非 usage / 非法 JSON 返回 None。"""
    if not payload or payload == "[DONE]":
        return None
    try:
        obj = json.loads(payload)
    except (ValueError, TypeError):
        return None
    usage = obj.get("usage")
    if not isinstance(usage, dict):
        return None
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
    }


async def _backfill_log_usage(log_id: int, usage: dict, app_key_id: Optional[int] = None) -> None:
    """流式响应结束后，把解析到的真实 token 用量回填到请求日志行。

    同时累计 `app_key.token_used`（token_quota 配额的依据）——流式请求的用量
    只有流结束才知道，所以两件事必须在同一个事务里做，避免"日志有量、配额没扣"。
    """
    if not log_id or not usage:
        return
    async with async_session() as session:
        await session.execute(
            update(ApiRequestLog)
            .where(ApiRequestLog.id == log_id)
            .values(
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["prompt_tokens"] + usage["completion_tokens"],
            )
        )
        if app_key_id:
            await session.execute(
                update(AppKey)
                .where(AppKey.id == app_key_id)
                .values(
                    token_used=AppKey.token_used
                    + int(usage["prompt_tokens"])
                    + int(usage["completion_tokens"])
                )
            )
        await session.commit()


async def _relay_sse_stream(upstream, log_id: Optional[int], app_key_id: Optional[int] = None):
    """透传上游 SSE 字节流，同时旁路解析 data 事件里的 usage（Token 统计用）。

    - 对客户端完全透明：原始字节逐个透传，不做重编码/缓存整流；
    - 流正常结束后用解析到的真实 usage 回填请求日志（取最后一条 usage）；
    - 客户端中途断开 / 上游异常：关闭连接，保留起始时记录的 0-token 行
      （请求数不丢，只是无用量可回填）；
    - 只关闭上游 response，**不关闭**共享 HTTP 客户端（否则会掐断整个连接池）。
    """
    usage: Optional[dict] = None
    buf = ""
    try:
        async for chunk in upstream.aiter_bytes():
            yield chunk
            # 旁路解析：逐行匹配 data: 载荷，不回写、不改动透传内容
            buf += chunk.decode("utf-8", errors="ignore")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.rstrip("\r")
                if not line.startswith("data:"):
                    continue
                parsed = _parse_usage_payload(line[5:].strip())
                if parsed:
                    usage = parsed
    finally:
        await upstream.aclose()

    if usage:
        await _backfill_log_usage(log_id, usage, app_key_id)


@router.get("/v1/models")
async def list_models_openai(db: AsyncSession = Depends(get_db)):
    """OpenAI 兼容模型列表（供 Dify/CherryStudio 等客户端拉取/校验连通性）。"""
    import time
    svc = ProxyService(db)
    models = await svc.list_online_models()
    return {
        "object": "list",
        "data": [
            {
                "id": m.name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ai-gateway-platform",
            }
            for m in models
        ],
    }


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, db: AsyncSession = Depends(get_db)):
    start = time.time()

    # 压测流量标记：只抑制 api_request_log 写入，鉴权/限流/路由照常
    is_perf_test = _is_perf_test_request(request.headers)
    svc = ProxyService(db, suppress_request_log=is_perf_test)

    # 1) 解析请求体
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "invalid json", "type": "invalid_request_error"}})

    model_name = (body or {}).get("model", "")
    raw_key = _extract_bearer(request)
    client_ip = request.client.host if request.client else None

    # 2) 校验平台 Key
    key = await svc.authenticate_key(raw_key) if raw_key else None
    if not key:
        return JSONResponse(
            status_code=401,
            content={"error": {"message": "Invalid or missing API key", "type": "authentication_error"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2.5) QPS 限流（Key 鉴权通过后计数：全局 → 单 Key）
    gw = GatewayService(db)
    global_qps, default_key_qps = await gw.get_effective_qps_limits()
    key_qps = key.qps_limit if key.qps_limit is not None else default_key_qps
    allowed, retry_after = await check_qps(
        global_limit=global_qps, key_id=key.id, key_limit=key_qps
    )
    if not allowed:
        resp = JSONResponse(
            status_code=429,
            content={"error": {"message": "rate limit exceeded", "type": "rate_limit_error"}},
        )
        resp.headers["Retry-After"] = str(retry_after or 1)
        return resp

    # 2.6) Key 级配额（只在 Key 显式设置上限时生效，NULL = 不限）：
    #      - rpm_limit / rpd_limit：分钟、东八区自然日请求数（Redis 固定窗口）
    #      - token_quota：累计 token 配额（用已加载的 key.token_used 判断，不额外查库）
    window_ok, window_retry = await check_key_windows(
        key_id=key.id, rpm_limit=key.rpm_limit, rpd_limit=key.rpd_limit
    )
    if not window_ok:
        resp = JSONResponse(
            status_code=429,
            content={
                "error": {
                    "message": "request quota exceeded (rpm/rpd)",
                    "type": "rate_limit_error",
                }
            },
        )
        resp.headers["Retry-After"] = str(window_retry or 1)
        return resp

    token_ok, _ = check_token_quota(token_used=key.token_used, token_quota=key.token_quota)
    if not token_ok:
        # 与 OpenAI 语义对齐：配额用尽返回 429 + insufficient_quota（不是 403）
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "message": "token quota exhausted, please contact platform admin",
                    "type": "insufficient_quota",
                }
            },
        )

    # 3) 解析目标模型：优先命中启用路由（同一逻辑模型的多实例策略组），
    #    未命中任何路由/目标时回退到现有"按 model 名直连"行为（不影响既有调用）
    route_id = None
    route_strategy = None
    matched = await gw.route_model_for(request.url.path, model_name)
    if matched and matched[2] is not None:
        route_id, route_strategy, model = matched
    else:
        model = await svc.resolve_model(model_name)
    if not model:
        return JSONResponse(
            status_code=404,
            content={"error": {"message": f"Model '{model_name}' not found or not online", "type": "invalid_request_error"}},
        )

    # 4) Key 权限校验（路由选中与直连命中的模型都校验）
    if not await svc.key_can_access_model(key.id, model.id):
        return JSONResponse(
            status_code=403,
            content={"error": {"message": f"Key has no access to model '{model_name}'", "type": "permission_error"}},
        )

    # 5) 注入部署级配置（system prompt / tools / 采样参数）——仅对部署模块注册的模型生效
    deploy_cfg = await svc.get_deployment_config(model.id)
    if deploy_cfg is not None:
        body = _apply_deployment_config(body, deploy_cfg)

    # 6) 转发到模型上游（流式 / 非流式两条路径）
    request_id = f"req_{uuid.uuid4().hex[:16]}"
    path = "/v1/chat/completions"

    # ---- 流式（DSH/客户端 stream:true）：SSE 透传 + 旁路解析 usage 用于 Token 统计 ----
    if (body or {}).get("stream"):
        # OpenAI 兼容上游在流式响应里默认不返回 usage；注入 include_usage 让其返回，
        # 否则无论怎么解析都拿不到 token 用量
        req_body, injected = _ensure_include_usage(body)
        try:
            upstream = await svc.open_stream(model, req_body)
        except httpx.TimeoutException:
            fo = await _standby_failover(svc, gw, request.url.path, model_name, model, req_body, stream=True)
            if fo is None:
                await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                         request_path=path, route_rule_id=route_id, status_code=504, client_ip=client_ip)
                await db.commit()
                return JSONResponse(status_code=504, content={"error": {"message": "upstream timeout", "type": "timeout_error"}})
            upstream, model = fo
        except httpx.HTTPError as e:
            logger_warn(e)
            fo = await _standby_failover(svc, gw, request.url.path, model_name, model, req_body, stream=True)
            if fo is None:
                await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                         request_path=path, route_rule_id=route_id, status_code=502, client_ip=client_ip)
                await db.commit()
                return JSONResponse(status_code=502, content={"error": {"message": "upstream error", "type": "upstream_error"}})
            upstream, model = fo

        # 注入的 stream_options 被上游拒绝（4xx 非 SSE）→ 用原请求体重试一次，保持兼容
        content_type = upstream.headers.get("content-type", "")
        if injected and upstream.status_code >= 400 and "text/event-stream" not in content_type:
            await upstream.aclose()
            try:
                upstream = await svc.open_stream(model, body)
                content_type = upstream.headers.get("content-type", "")
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                logger_warn(e)
                await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                         request_path=path, route_rule_id=route_id, status_code=502, client_ip=client_ip)
                await db.commit()
                return JSONResponse(status_code=502, content={"error": {"message": "upstream error", "type": "upstream_error"}})

        # 上游 4xx/5xx 非 SSE 错误：读出错误体返回，并记一条失败请求日志（请求量统计完整）
        if upstream.status_code >= 400 and "text/event-stream" not in content_type:
            try:
                err_body = await upstream.aread()
            finally:
                await upstream.aclose()
            await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                     request_path=path, route_rule_id=route_id,
                                     response_time_ms=int((time.time() - start) * 1000),
                                     status_code=upstream.status_code, client_ip=client_ip)
            await db.commit()
            return JSONResponse(status_code=upstream.status_code, content=err_body)

        # 先记一条日志（起始未知用量）：保证客户端断开/出错时请求数不丢；
        # 流正常结束后由 _relay_sse_stream 用解析到的真实 usage 回填该行 token
        log = await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                       request_path=path, route_rule_id=route_id,
                                       response_time_ms=int((time.time() - start) * 1000),
                                       status_code=upstream.status_code, client_ip=client_ip)
        await db.commit()
        log_id = log.id if log else None

        # ⚠️ 关键：长时间 SSE 转发前归还数据库连接。
        # 否则一条 30~60 秒的流会独占一条连接，高并发下迅速耗尽连接池，
        # 表现为新请求排队变慢甚至 "too many clients already"。
        await db.close()

        return StreamingResponse(
            _relay_sse_stream(upstream, log_id, key.id),
            status_code=upstream.status_code,
            media_type=content_type or "text/event-stream",
        )

    # ---- 非流式 ----
    # ⚠️ 与上面流式分支同一个道理，但更隐蔽：非流式请求要从头等到上游把整段回答
    # 生成完（几十秒到几分钟都可能）。这期间若仍持有数据库连接，并发上限会被
    # 连接池锁死为 (DB_POOL_SIZE + DB_MAX_OVERFLOW) × worker 数，超出的请求只能
    # 排队，最后以 "QueuePool limit ... connection timed out" 500 收场。
    # 先归还连接，拿到上游响应后 record_request 会自动重新取一条。
    # Session.close() 之后仍可继续使用，且 expire_on_commit=False，此处 key/model
    # 已加载的字段（id、api_base_url 等）保持可用。
    await db.close()

    try:
        upstream = await svc.forward(model, body)
    except httpx.TimeoutException:
        fo = await _standby_failover(svc, gw, request.url.path, model_name, model, body, stream=False)
        if fo is None:
            await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                     request_path=path, route_rule_id=route_id, status_code=504, client_ip=client_ip)
            await db.commit()
            return JSONResponse(status_code=504, content={"error": {"message": "upstream timeout", "type": "timeout_error"}})
        upstream, model = fo
    except httpx.HTTPError as e:
        logger_warn(e)
        fo = await _standby_failover(svc, gw, request.url.path, model_name, model, body, stream=False)
        if fo is None:
            await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                     request_path=path, route_rule_id=route_id, status_code=502, client_ip=client_ip)
            await db.commit()
            return JSONResponse(status_code=502, content={"error": {"message": "upstream error", "type": "upstream_error"}})
        upstream, model = fo

    # 6) 记录用量日志
    cost_ms = int((time.time() - start) * 1000)
    try:
        resp_json = upstream.json()
        usage = _usage_from_body(resp_json)
    except Exception:
        resp_json = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0}

    # 累计 Key 已用 token（token_quota 依据），与日志写入同一事务
    await svc.add_token_used(
        key.id, usage["prompt_tokens"] + usage["completion_tokens"]
    )
    await svc.record_request(
        request_id=request_id,
        app_key_id=key.id,
        model_id=model.id,
        request_path=path,
        route_rule_id=route_id,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        response_time_ms=cost_ms,
        status_code=upstream.status_code,
        client_ip=client_ip,
    )
    await db.commit()

    # 7) 返回（透传上游 JSON 响应）
    if resp_json is None:
        resp_json = {"error": {"message": "upstream returned invalid json", "type": "upstream_error"}}
    return JSONResponse(status_code=upstream.status_code, content=resp_json)


async def _standby_failover(svc, gw, path: str, model_name: str, failed_model, body: dict, *, stream: bool):
    """主备路由连接级失败后的故障切换：排除故障目标，按策略重选一台并重连。

    只在 active_standby 路由上生效；返回 None 表示无可用备机（调用方返回 502/504）。
    生成完成后的 5xx 不在此重试（避免重复计费）。
    """
    route_id, strategy, alt = await gw.route_model_for(path, model_name, exclude_model_id=failed_model.id)
    if route_id is None or strategy != "active_standby" or alt is None or alt.id == failed_model.id:
        return None

    # 选路查询已结束：立刻归还连接再重连备机。否则一次切换失败的上游
    # 会让每个请求在「重连 + 生成」阶段又长期占住一条连接（同上面非流式的坑）。
    await svc.db.close()

    try:
        if stream:
            resp = await svc.open_stream(alt, body)
        else:
            resp = await svc.forward(alt, body)
        return resp, alt
    except (httpx.TimeoutException, httpx.HTTPError):
        return None


def logger_warn(exc: Exception) -> None:
    import logging
    logging.getLogger(__name__).warning("upstream error: %s", exc)
