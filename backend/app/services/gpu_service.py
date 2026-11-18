"""GPU 资源采集。

采集优先级：
  1) pynvml（NVIDIA 官方 Python 绑定，最稳）
  2) nvidia-smi 子进程解析（pynvml 未安装时的兜底）
  3) 都不可用 → 返回 available=False + 原因，不抛异常

为什么要区分来源：api-server 容器默认没有 GPU，采集一定失败；实际采集应跑在
有 GPU 的 worker（quantization 队列）里，把结果写 Redis，API 读缓存。
见 app/tasks/deployment_tasks.py::collect_gpu_stats。
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.redis import redis_client
from app.schemas.deployment import GpuTopology

logger = logging.getLogger(__name__)

GPU_CACHE_KEY = "gw:gpu:topology"

_NVIDIA_SMI_ARGS = [
    "nvidia-smi",
    "--query-gpu=index,memory.total,memory.used,memory.free",
    "--format=csv,noheader,nounits",
]

# MiB → GB
_MIB_PER_GB = 1024.0


def _round2(value: float) -> float:
    return round(float(value), 2)


def parse_nvidia_smi_csv(text: str) -> list[dict]:
    """解析 `nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free` 输出。

    输入形如: "0, 46068, 1234, 44834"（每行一张卡，单位 MiB）。
    非法行跳过；字段缺失的行跳过。
    """
    gpus: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            index = int(parts[0])
            total_mib = float(parts[1])
            used_mib = float(parts[2])
            free_mib = float(parts[3])
        except (TypeError, ValueError):
            continue
        # 某些驱动在遇到 [N/A] 时会返回非数字，上面已跳过
        gpus.append(
            {
                "gpu_id": index,
                "memory_total_gb": _round2(total_mib / _MIB_PER_GB),
                "memory_used_gb": _round2(used_mib / _MIB_PER_GB),
                "memory_free_gb": _round2(free_mib / _MIB_PER_GB),
            }
        )
    return gpus


def _collect_via_nvml() -> Optional[list[dict]]:
    """用 pynvml 采集；不可用时返回 None。"""
    try:
        import pynvml  # nvidia-ml-py
    except ImportError:
        return None

    try:
        pynvml.nvmlInit()
    except Exception:
        logger.debug("[gpu] nvmlInit failed", exc_info=True)
        return None

    try:
        count = pynvml.nvmlDeviceGetCount()
        gpus = []
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpus.append(
                {
                    "gpu_id": i,
                    "memory_total_gb": _round2(mem.total / (1024**3)),
                    "memory_used_gb": _round2(mem.used / (1024**3)),
                    "memory_free_gb": _round2(mem.free / (1024**3)),
                }
            )
        return gpus
    except Exception:
        logger.debug("[gpu] nvml query failed", exc_info=True)
        return None
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def _collect_via_smi() -> Optional[list[dict]]:
    """用 nvidia-smi 子进程采集；失败返回 None。"""
    try:
        proc = subprocess.run(
            _NVIDIA_SMI_ARGS,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        logger.debug("[gpu] nvidia-smi exit %s: %s", proc.returncode, proc.stderr[:200])
        return None
    return parse_nvidia_smi_csv(proc.stdout)


def collect_local() -> tuple[bool, str, Optional[str], list[dict]]:
    """本机采集一次。

    返回 (available, source, error, gpus)。
    """
    gpus = _collect_via_nvml()
    if gpus is not None:
        return True, "nvml", None, gpus

    gpus = _collect_via_smi()
    if gpus is not None:
        return True, "nvidia-smi", None, gpus

    return False, "none", "本机无法采集 GPU（pynvml 未安装且 nvidia-smi 不可用）", []


async def publish_snapshot(gpus: list[dict], source: str) -> None:
    """把采集结果写入 Redis 缓存（供 API 读取）。"""
    payload = {
        "available": True,
        "source": source,
        "error": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "gpus": gpus,
    }
    try:
        await redis_client.set(
            GPU_CACHE_KEY, json.dumps(payload), ex=settings.gpu_stats_ttl_seconds
        )
    except Exception:
        logger.warning("[gpu] publish snapshot to redis failed", exc_info=True)


async def read_snapshot() -> Optional[dict]:
    """从 Redis 读缓存；没有/过期返回 None。"""
    try:
        raw = await redis_client.get(GPU_CACHE_KEY)
    except Exception:
        logger.debug("[gpu] read snapshot from redis failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def to_topology(gpus: list[dict], deployment_map: Optional[dict[int, list[str]]] = None) -> list[GpuTopology]:
    """把原始 GPU 数据转成响应对象，并挂上"该卡上跑着哪些部署"。"""
    deployment_map = deployment_map or {}
    result: list[GpuTopology] = []
    for g in gpus:
        gid = int(g.get("gpu_id", 0))
        result.append(
            GpuTopology(
                gpu_id=gid,
                memory_total_gb=float(g.get("memory_total_gb") or 0),
                memory_used_gb=float(g.get("memory_used_gb") or 0),
                memory_free_gb=float(g.get("memory_free_gb") or 0),
                deployments=deployment_map.get(gid, []),
            )
        )
    return result
