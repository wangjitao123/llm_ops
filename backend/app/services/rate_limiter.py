"""统一网关 QPS 限流（Redis 固定窗口，按当前秒计数，跨 worker 准确）。

- 全局限额与单 Key 限额独立计数，任一超限即拒绝（429）；
- 鉴权失败不计入（限流在 Key 鉴权通过后调用）；
- Redis 异常时放行（fail-open）并告警，避免网关不可用。
"""
import logging
import time
from typing import Optional

from app.core.redis import redis_client

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 1   # 固定窗口：1 秒
_EXPIRE_SECONDS = 2   # 计数 key 留存时间（略大于窗口即可）


async def check_qps(
    *,
    global_limit: Optional[int] = None,
    key_id: Optional[int] = None,
    key_limit: Optional[int] = None,
) -> tuple[bool, int]:
    """按当前秒计数并判断是否放行。

    返回 (allowed, retry_after_seconds)；allowed=False 时应返回 429。
    """
    if (not global_limit) and (not key_id or not key_limit):
        return True, 0

    now_s = int(time.time())
    try:
        pipe = redis_client.pipeline()
        if global_limit:
            pipe.incr(f"gw:rl:g:{now_s}")
            pipe.expire(f"gw:rl:g:{now_s}", _EXPIRE_SECONDS)
        if key_id and key_limit:
            pipe.incr(f"gw:rl:k:{key_id}:{now_s}")
            pipe.expire(f"gw:rl:k:{key_id}:{now_s}", _EXPIRE_SECONDS)
        results = await pipe.execute()
    except Exception:
        # fail-open：Redis 不可用时放行，避免网关整体不可用
        logger.warning("[rate-limit] redis error, request allowed", exc_info=True)
        return True, 0

    idx = 0
    if global_limit:
        if int(results[idx]) > int(global_limit):
            return False, _WINDOW_SECONDS
        idx += 2
    if key_id and key_limit:
        if int(results[idx]) > int(key_limit):
            return False, _WINDOW_SECONDS
    return True, 0
