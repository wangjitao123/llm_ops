"""网关到上游模型的共享 HTTP 客户端。

为什么共享而不是每请求新建：
  httpx.AsyncClient 关闭即断开 TCP 连接。每请求 `async with AsyncClient(...)`
  意味着每个请求都要重新 TCP 握手（跨机 HTTPS 还要 TLS 握手），高并发下
  这部分开销会显著抬高 P99。共享一个客户端可复用连接池（keep-alive）。

注意：流式响应结束时只能关闭 `response`，绝不能关闭这个共享客户端。
"""
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """取（首次调用时创建）全局共享 AsyncClient。"""
    global _client
    if _client is None:
        timeout = httpx.Timeout(
            connect=settings.http_connect_timeout,
            read=settings.http_read_timeout,
            write=settings.http_read_timeout,
            pool=settings.http_read_timeout,
        )
        _client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=settings.http_pool_max_connections,
                max_keepalive_connections=settings.http_pool_max_keepalive,
            ),
        )
        logger.info(
            "[http] shared client created (max_conn=%d, keepalive=%d)",
            settings.http_pool_max_connections,
            settings.http_pool_max_keepalive,
        )
    return _client


async def close_http_client() -> None:
    """应用关闭时释放连接池。"""
    global _client
    if _client is not None:
        client, _client = _client, None
        try:
            await client.aclose()
        except Exception:  # pragma: no cover - 关闭失败不影响进程退出
            logger.warning("[http] close shared client failed", exc_info=True)
