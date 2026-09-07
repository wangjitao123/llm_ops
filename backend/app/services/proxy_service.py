"""网关代理服务：平台作为 OpenAI 兼容的统一模型入口。

核心链路（用户诉求）：
  应用/开发者
    │  携带平台分配的 Key (Authorization: Bearer sk-xxx) 调用平台 OpenAI 兼容入口
    ▼
  平台后端 /v1/chat/completions
    │  1) 校验平台 Key（是否有效/未过期/状态 active）
    │  2) 按请求体 model 名解析目标模型（model 表）
    │  3) 校验该 Key 是否有权访问该模型（app_key_model）
    │  4) 转发到模型配置的 api_base_url（本地模型可无 Key）
    ▼
  本地/远程模型服务
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.key import AppKey, AppKeyModel
from app.models.model import Model
from app.models.token import ApiRequestLog

logger = logging.getLogger(__name__)

# 常见 OpenAI 兼容服务路径片段（本地 vLLM/Ollama/OneAPI 等）
CHAT_PATH = "/chat/completions"


class ProxyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- Key 鉴权 ----------
    async def authenticate_key(self, raw_key: str) -> Optional[AppKey]:
        """校验平台 Key 有效性（哈希比对 + 状态 + 过期检查）。无效返回 None。"""
        if not raw_key:
            return None
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        result = await self.db.execute(
            select(AppKey).where(AppKey.key_hash == key_hash, AppKey.deleted_at.is_(None))
        )
        key = result.scalar_one_or_none()
        if not key or key.status != "active":
            return None
        if key.expires_at and key.expires_at < datetime.now(timezone.utc):
            key.status = "expired"
            await self.db.flush()
            return None
        key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
        return key

    async def resolve_model(self, model_name: str) -> Optional[Model]:
        """按请求 model 名解析目标模型（当前模型在线才可用）。"""
        if not model_name:
            return None
        result = await self.db.execute(
            select(Model).where(
                Model.name == model_name,
                Model.deleted_at.is_(None),
                Model.status == "online",
            )
        )
        return result.scalar_one_or_none()

    async def list_online_models(self) -> list[Model]:
        """列出全部在线模型（供 OpenAI 兼容 /v1/models 端点）。"""
        result = await self.db.execute(
            select(Model).where(
                Model.deleted_at.is_(None),
                Model.status == "online",
            ).order_by(Model.created_at)
        )
        return list(result.scalars().all())

    async def key_can_access_model(self, key_id: int, model_id: int) -> bool:
        """Key 是否有权访问该模型：未绑定任何模型 = 全部放行；绑定了则须包含。"""
        result = await self.db.execute(
            select(AppKeyModel).where(AppKeyModel.app_key_id == key_id)
        )
        perms = result.scalars().all()
        if not perms:
            return True  # 未绑定限制，默认放行
        return any(p.model_id == model_id for p in perms)

    async def list_key_allowed_model_ids(self, key_id: int) -> list[int] | None:
        """返回 Key 可访问的模型 id 列表；None 表示未限制（全部放行）。"""
        result = await self.db.execute(
            select(AppKeyModel).where(AppKeyModel.app_key_id == key_id)
        )
        perms = result.scalars().all()
        if not perms:
            return None
        return [p.model_id for p in perms]

    # ---------- 请求转发 ----------
    async def forward(
        self,
        model: Model,
        body: dict,
        timeout: float = 120.0,
    ) -> httpx.Response:
        """把 OpenAI 兼容请求体转发到模型 api_base_url，返回上游响应。

        - 模型配置了 API Key（api_key_encrypted 非空）→ 携带 Authorization Bearer；
        - 本地模型无 Key（api_key_encrypted 为空）→ 不携带，直接转发。
        """
        base = model.api_base_url.rstrip("/")
        url = f"{base}{CHAT_PATH}"
        headers = {"Content-Type": "application/json"}
        if model.api_key_encrypted:
            headers["Authorization"] = f"Bearer {model.api_key_encrypted}"

        # 透传必要参数（model/messages/temperature 等由应用侧传入）
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
        return resp

    async def record_request(
        self,
        *,
        request_id: str,
        app_key_id: Optional[int],
        model_id: Optional[int],
        request_path: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        response_time_ms: int = 0,
        status_code: int = 200,
        client_ip: Optional[str] = None,
    ) -> None:
        """记录一次网关请求日志（供 Token 统计/审计使用）。"""
        log = ApiRequestLog(
            request_id=request_id,
            app_key_id=app_key_id,
            model_id=model_id,
            request_path=request_path,
            request_method="POST",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            response_time_ms=response_time_ms,
            status_code=status_code,
            client_ip=client_ip,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(log)
        await self.db.flush()
