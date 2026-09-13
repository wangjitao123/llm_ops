"""OpenAI 兼容统一入口（供外部应用调用平台模型）。

这就是用户诉求的落地：
  应用带平台 Key（Authorization: Bearer sk-xxx）+ OpenAI 格式请求体
  → POST {平台地址}/v1/chat/completions
  → 平台校验 Key → 解析模型 → 转发本地模型（无 Key）→ 返回 OpenAI 格式响应
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
from app.models.token import ApiRequestLog
from app.services.gateway_service import GatewayService
from app.services.proxy_service import ProxyService
from app.services.rate_limiter import check_qps

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


async def _backfill_log_usage(log_id: int, usage: dict) -> None:
    """流式响应结束后，把解析到的真实 token 用量回填到请求日志行。"""
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
        await session.commit()


async def _relay_sse_stream(upstream, http_client, log_id: Optional[int]):
    """透传上游 SSE 字节流，同时旁路解析 data 事件里的 usage（Token 统计用）。

    - 对客户端完全透明：原始字节逐个透传，不做重编码/缓存整流；
    - 流正常结束后用解析到的真实 usage 回填请求日志（取最后一条 usage）；
    - 客户端中途断开 / 上游异常：关闭连接，保留起始时记录的 0-token 行
      （请求数不丢，只是无用量可回填）。
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
        try:
            await upstream.aclose()
        finally:
            await http_client.aclose()

    if usage:
        await _backfill_log_usage(log_id, usage)


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
    svc = ProxyService(db)
    start = time.time()

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

    # 5) 转发到模型上游（流式 / 非流式两条路径）
    request_id = f"req_{uuid.uuid4().hex[:16]}"
    path = "/v1/chat/completions"

    # ---- 流式（DSH/客户端 stream:true）：SSE 透传 + 旁路解析 usage 用于 Token 统计 ----
    if (body or {}).get("stream"):
        # OpenAI 兼容上游在流式响应里默认不返回 usage；注入 include_usage 让其返回，
        # 否则无论怎么解析都拿不到 token 用量
        req_body, injected = _ensure_include_usage(body)
        try:
            http_client, upstream = await svc.open_stream(model, req_body)
        except httpx.TimeoutException:
            fo = await _standby_failover(svc, gw, request.url.path, model_name, model, req_body, stream=True)
            if fo is None:
                await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                         request_path=path, route_rule_id=route_id, status_code=504, client_ip=client_ip)
                await db.commit()
                return JSONResponse(status_code=504, content={"error": {"message": "upstream timeout", "type": "timeout_error"}})
            http_client, upstream, model = fo
        except httpx.HTTPError as e:
            logger_warn(e)
            fo = await _standby_failover(svc, gw, request.url.path, model_name, model, req_body, stream=True)
            if fo is None:
                await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                         request_path=path, route_rule_id=route_id, status_code=502, client_ip=client_ip)
                await db.commit()
                return JSONResponse(status_code=502, content={"error": {"message": "upstream error", "type": "upstream_error"}})
            http_client, upstream, model = fo

        # 注入的 stream_options 被上游拒绝（4xx 非 SSE）→ 用原请求体重试一次，保持兼容
        content_type = upstream.headers.get("content-type", "")
        if injected and upstream.status_code >= 400 and "text/event-stream" not in content_type:
            await upstream.aclose()
            await http_client.aclose()
            try:
                http_client, upstream = await svc.open_stream(model, body)
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
                await http_client.aclose()
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

        return StreamingResponse(
            _relay_sse_stream(upstream, http_client, log.id if log else None),
            status_code=upstream.status_code,
            media_type=content_type or "text/event-stream",
        )

    # ---- 非流式 ----
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
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
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

    # 7) 返回（暂透传 JSON；流式待二期实现）
    return JSONResponse(status_code=upstream.status_code, content=upstream.json())


async def _standby_failover(svc, gw, path: str, model_name: str, failed_model, body: dict, *, stream: bool):
    """主备路由连接级失败后的故障切换：排除故障目标，按策略重选一台并重连。

    只在 active_standby 路由上生效；返回 None 表示无可用备机（调用方返回 502/504）。
    生成完成后的 5xx 不在此重试（避免重复计费）。
    """
    route_id, strategy, alt = await gw.route_model_for(path, model_name, exclude_model_id=failed_model.id)
    if route_id is None or strategy != "active_standby" or alt is None or alt.id == failed_model.id:
        return None
    try:
        if stream:
            client, resp = await svc.open_stream(alt, body)
            return (client, resp, alt)
        resp = await svc.forward(alt, body)
        return (resp, alt)
    except (httpx.TimeoutException, httpx.HTTPError):
        return None


def logger_warn(exc: Exception) -> None:
    import logging
    logging.getLogger(__name__).warning("upstream error: %s", exc)
