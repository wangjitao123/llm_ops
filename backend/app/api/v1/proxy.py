"""OpenAI 兼容统一入口（供外部应用调用平台模型）。

这就是用户诉求的落地：
  应用带平台 Key（Authorization: Bearer sk-xxx）+ OpenAI 格式请求体
  → POST {平台地址}/v1/chat/completions
  → 平台校验 Key → 解析模型 → 转发本地模型（无 Key）→ 返回 OpenAI 格式响应
"""
import time
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.proxy_service import ProxyService

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

    # 3) 解析目标模型
    model = await svc.resolve_model(model_name)
    if not model:
        return JSONResponse(
            status_code=404,
            content={"error": {"message": f"Model '{model_name}' not found or not online", "type": "invalid_request_error"}},
        )

    # 4) Key 权限校验
    if not await svc.key_can_access_model(key.id, model.id):
        return JSONResponse(
            status_code=403,
            content={"error": {"message": f"Key has no access to model '{model_name}'", "type": "permission_error"}},
        )

    # 5) 转发到模型上游
    request_id = f"req_{uuid.uuid4().hex[:16]}"
    path = f"/v1/chat/completions"
    try:
        upstream = await svc.forward(model, body)
    except httpx.TimeoutException:
        await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                 request_path=path, status_code=504, client_ip=client_ip)
        return JSONResponse(status_code=504, content={"error": {"message": "upstream timeout", "type": "timeout_error"}})
    except httpx.HTTPError as e:
        logger_warn(e)
        await svc.record_request(request_id=request_id, app_key_id=key.id, model_id=model.id,
                                 request_path=path, status_code=502, client_ip=client_ip)
        return JSONResponse(status_code=502, content={"error": {"message": "upstream error", "type": "upstream_error"}})

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
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        response_time_ms=cost_ms,
        status_code=upstream.status_code,
        client_ip=client_ip,
    )
    await db.commit()

    # 7) 返回（暂透传 JSON；流式待二期实现）
    return JSONResponse(status_code=upstream.status_code, content=upstream.json())


def logger_warn(exc: Exception) -> None:
    import logging
    logging.getLogger(__name__).warning("upstream error: %s", exc)
