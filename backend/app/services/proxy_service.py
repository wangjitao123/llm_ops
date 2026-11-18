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
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.http import get_http_client
from app.core.redis import redis_client
from app.models.key import AppKey, AppKeyModel
from app.models.model import Model
from app.models.token import ApiRequestLog

logger = logging.getLogger(__name__)

# 常见 OpenAI 兼容服务路径片段（本地 vLLM/Ollama/OneAPI 等）
CHAT_PATH = "/chat/completions"


class ProxyService:
    def __init__(self, db: AsyncSession, suppress_request_log: bool = False):
        self.db = db
        # 压测流量标记（ADR-004 / M04 方案3）：
        # True 时**只跳过 api_request_log 写入**，鉴权/限流/路由完全照常执行。
        # 这样伪造 X-Perf-Test 头也拿不到额外配额，只是自己的请求不进报表。
        self.suppress_request_log = suppress_request_log

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

        # last_used_at 降频落库：高并发下每请求一次 UPDATE 会白白压数据库。
        # 用 Redis 标记做节流（窗口内只写一次），Redis 不可用时退化为每请求写。
        await self._touch_last_used(key)
        return key

    async def _touch_last_used(self, key: AppKey) -> None:
        """刷新 Key 的最后使用时间，按 settings.key_last_used_throttle_seconds 降频。"""
        throttle = settings.key_last_used_throttle_seconds
        now = datetime.now(timezone.utc)

        if throttle <= 0 or key.id is None:
            key.last_used_at = now
            await self.db.flush()
            return

        try:
            # nx=True：只有本窗口第一个请求能拿到 True，后续请求跳过写库
            is_first_in_window = await redis_client.set(
                f"gw:keylast:{key.id}", "1", ex=throttle, nx=True
            )
        except Exception:
            logger.warning("[last-used] redis unavailable, write every request", exc_info=True)
            key.last_used_at = now
            await self.db.flush()
            return

        if is_first_in_window:
            key.last_used_at = now
            await self.db.flush()

    async def resolve_model(self, model_name: str) -> Optional[Model]:
        """按请求 model 名解析目标模型（当前模型在线才可用）。

        同一 model 名允许注册多个实例（路由分发场景），直连时取 id 最小者。
        """
        if not model_name:
            return None
        result = await self.db.execute(
            select(Model).where(
                Model.name == model_name,
                Model.deleted_at.is_(None),
                Model.status == "online",
            ).order_by(Model.id).limit(1)
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

    async def get_deployment_config(self, model_id: int):
        """查该模型对应的「在跑的部署」，用于注入 system prompt / tools / 采样参数。

        只有由部署模块自动注册（registered_model_id 命中）且运行中的部署才返回。
        """
        from app.models.deployment import Deployment

        result = await self.db.execute(
            select(Deployment)
            .where(
                Deployment.registered_model_id == model_id,
                Deployment.deleted_at.is_(None),
                Deployment.status == "running",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

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
        - 复用全局共享 AsyncClient（keep-alive），不再每请求新建连接。
        """
        base = model.api_base_url.rstrip("/")
        url = f"{base}{CHAT_PATH}"
        headers = {"Content-Type": "application/json"}
        if model.api_key_encrypted:
            headers["Authorization"] = f"Bearer {model.api_key_encrypted}"

        client = get_http_client()
        resp = await client.post(url, json=body, headers=headers, timeout=timeout)
        return resp

    async def open_stream(
        self,
        model: Model,
        body: dict,
    ) -> httpx.Response:
        """流式转发（SSE）：返回上游 streaming response，调用方负责结束后 aclose 它。

        注意两点：
          1. 只关闭 response，**不要**关闭共享客户端（见 app/core/http.py）。
          2. `httpx.AsyncClient.send()` **不支持 per-request timeout**
             （只有 post/request/stream 支持），流式请求使用共享客户端的默认超时
             —— 即 settings.http_read_timeout（默认 300s，作用于两次 chunk 之间）。
             原先这里传了 timeout= 会导致 TypeError，已移除。
        """
        base = model.api_base_url.rstrip("/")
        url = f"{base}{CHAT_PATH}"
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if model.api_key_encrypted:
            headers["Authorization"] = f"Bearer {model.api_key_encrypted}"

        client = get_http_client()
        req = client.build_request("POST", url, json=body, headers=headers)
        return await client.send(req, stream=True)

    async def add_token_used(self, key_id: Optional[int], tokens: int) -> None:
        """累计 Key 的已用 token —— `token_quota` 配额的判断依据。

        两点约定：
          * 压测流量（suppress_request_log=True）不记账，与"压测不进报表"的
            隔离策略保持一致，否则压测会把真实 Key 的配额打爆；
          * 用 `UPDATE ... token_used = token_used + n` 原子累加，
            避免"读-改-写"在并发下丢更新。
        """
        if not key_id or not tokens or self.suppress_request_log:
            return
        await self.db.execute(
            update(AppKey)
            .where(AppKey.id == key_id)
            .values(token_used=AppKey.token_used + int(tokens))
        )

    async def record_request(
        self,
        *,
        request_id: str,
        app_key_id: Optional[int],
        model_id: Optional[int],
        request_path: str,
        route_rule_id: Optional[int] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        response_time_ms: int = 0,
        status_code: int = 200,
        client_ip: Optional[str] = None,
    ) -> Optional[ApiRequestLog]:
        """记录一次网关请求日志（供 Token 统计/审计使用）。

        返回已 flush 的日志对象（流式请求需用其 id 在流结束后回填真实 token 用量）。

        **压测流量直接跳过**：`suppress_request_log=True` 时不写库并返回 None，
        调用方拿到的 log_id 为 None，流结束的 usage 回填也会自动跳过。
        """
        if self.suppress_request_log:
            return None

        log = ApiRequestLog(
            request_id=request_id,
            app_key_id=app_key_id,
            model_id=model_id,
            route_rule_id=route_rule_id,
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
        return log
