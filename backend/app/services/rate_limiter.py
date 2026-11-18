"""统一网关限流与配额（Redis 固定窗口，按当前秒/分/天计数，跨 worker 准确）。

- QPS：全局限额与单 Key 限额独立计数，任一超限即拒绝（429）；
- RPM / RPD：每分钟、每自然日（东八区）请求数，**只有 Key 显式设置了上限才生效**；
- Token 配额：累计用量达到上限即拒绝（429 insufficient_quota），纯函数、不查库；
- 鉴权失败不计入（判定都在 Key 鉴权通过后调用）；
- Redis 异常时放行（fail-open）并告警，避免网关不可用。
"""
import logging
import time
from typing import Optional

from app.core.redis import redis_client

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 1   # 固定窗口：1 秒
_EXPIRE_SECONDS = 2   # 计数 key 留存时间（略大于窗口即可）

# 统计口径统一用东八区（与 app/tasks/stats_aggregator.py 的 LOCAL_TZ 一致），
# 否则"每日请求数"会在北京时间早上 8 点重置，非常反直觉。
_TZ_OFFSET = 8 * 3600
_MINUTE = 60
_DAY = 86400


async def _incr_window(key: str, window_seconds: int) -> int:
    """在固定窗口内自增并返回当前计数；Redis 异常时返回 0（fail-open）。"""
    slot = int(time.time()) // window_seconds
    redis_key = f"{key}:{slot}"
    try:
        pipe = redis_client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds * 2)
        results = await pipe.execute()
        return int(results[0])
    except Exception:
        logger.warning("[rate-limit] redis error, window check skipped", exc_info=True)
        return 0


def _seconds_to_next_minute(now: int) -> int:
    return _MINUTE - (now % _MINUTE)


def _seconds_to_next_local_day(now: int) -> int:
    return _DAY - ((now + _TZ_OFFSET) % _DAY)


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


async def check_key_windows(
    *,
    key_id: Optional[int],
    rpm_limit: Optional[int] = None,
    rpd_limit: Optional[int] = None,
) -> tuple[bool, int]:
    """Key 级分钟 / 每日请求数配额。

    **NULL（None）= 不限制**，所以存量 Key 不会被这套新增规则影响。
    返回 (allowed, retry_after_seconds)。
    """
    if not key_id or (not rpm_limit and not rpd_limit):
        return True, 0

    now = int(time.time())
    rpm_used = await _incr_window(f"gw:rpm:{key_id}", _MINUTE) if rpm_limit else 0
    rpd_used = await _incr_window(f"gw:rpd:{key_id}", _DAY) if rpd_limit else 0

    if rpm_limit and rpm_used > int(rpm_limit):
        return False, _seconds_to_next_minute(now)
    if rpd_limit and rpd_used > int(rpd_limit):
        return False, _seconds_to_next_local_day(now)
    return True, 0


def check_token_quota(
    *,
    token_used: Optional[int],
    token_quota: Optional[int],
) -> tuple[bool, int]:
    """累计 token 配额判断（纯函数，利用已加载的 app_key 行，不额外查库）。

    NULL / 0 = 不限制。返回 (allowed, retry_after_seconds)；
    token 配额用尽后无法通过等待恢复，retry_after 固定 0。
    """
    if not token_quota or int(token_quota) <= 0:
        return True, 0
    if int(token_used or 0) >= int(token_quota):
        return False, 0
    return True, 0
