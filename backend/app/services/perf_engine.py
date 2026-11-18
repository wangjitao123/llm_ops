"""EvalScope 压测引擎适配层。

职责：把平台 `perf_task` 的参数翻译成 EvalScope 的 `Arguments`。

**参数映射依据**（逐项核对过 evalscope 源码 `evalscope/perf/arguments.py`）：

| 平台字段 | EvalScope 字段 | 说明 |
|----------|---------------|------|
| target_url | url | 完整到 /chat/completions |
| model_name_snapshot | model | 目标模型名 |
| dataset_type | dataset | random / openqa / ... |
| input_length | min_prompt_length + max_prompt_length | 两者取同值，保证负载长度确定 |
| output_length | min_tokens + max_tokens | 同上 |
| stream | stream | 是否流式（决定能否测 TTFT） |
| temperature | temperature | |
| tokenizer_path | tokenizer_path | 留空由 EvalScope 推断 |
| mode=closed_loop | parallel + number, open_loop=False | |
| mode=open_loop | open_loop=True + rate + number | |
| mode=sla | sla_auto_tune=True + sla_params + 上下界 | **注意：是上下界搜索，不是步进** |
| mode=multi_turn | multi_turn=True + min_turns/max_turns + parallel + number | |

**SLA 参数结构**（实测 `sla_run.parse_sla_params`）：
`sla_params` 是 `[{metric_name: "<= 500ms"}]` 形式的列表，
metric_name 必须是 `SLA_METRIC_FIELDS` 里的键（如 `p99_ttft`、`avg_ttft`、`p99_latency`）。

Phase 1 只实现参数翻译（纯函数，可单测）；真正的执行在 Phase 2 接入
`evalscope.perf.run_perf_benchmark()`。
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

CHAT_COMPLETIONS_PATH = "/chat/completions"

# 平台 SLA 指标 → EvalScope SLA metric 名（均取 P99 口径）
SLA_METRIC_MAP = {
    "ttft": "p99_ttft",
    "tpot": "p99_tpot",
    "latency": "p99_latency",
}

# SLA 模式未指定请求数时的默认单轮请求数
DEFAULT_SLA_NUMBER = 1000

# open_loop 模式下未指定并发上限时的默认值（仅作连接池上限）
DEFAULT_OPEN_LOOP_CONCURRENCY = 200


class PerfEngineUnavailable(RuntimeError):
    """压测引擎不可用（未安装 evalscope 或初始化失败）。"""


class PerfAborted(RuntimeError):
    """压测被用户中止（由父进程主动 terminate 子进程触发）。"""


class PerfRunFailed(RuntimeError):
    """压测执行失败（子进程返回 ok=false）。"""


def engine_available() -> tuple[bool, Optional[str]]:
    """探测 EvalScope 是否可用，返回 (available, error)。"""
    try:
        import evalscope  # noqa: F401
    except ImportError as e:
        return False, f"未安装 evalscope（{e}）"
    except Exception as e:  # noqa: BLE001 - 导入期异常一律视为不可用
        return False, f"导入 evalscope 失败：{e}"
    return True, None


def _get(task: Any, field: str, default=None):
    """兼容 ORM 对象与 dict。"""
    if isinstance(task, dict):
        return task.get(field, default)
    return getattr(task, field, default)


def build_sla_params(metric: str, threshold_ms: int) -> list[dict[str, str]]:
    """构造 EvalScope 的 sla_params。

    EvalScope 期望形如 ``[{"p99_ttft": "<= 500ms"}]``；
    表达式里的单位后缀会被其内部换算到指标原生单位。
    """
    metric_name = SLA_METRIC_MAP.get((metric or "").lower())
    if metric_name is None:
        raise ValueError(
            f"不支持的 SLA 指标: {metric}；可选: {', '.join(sorted(SLA_METRIC_MAP))}"
        )
    return [{metric_name: f"<= {int(threshold_ms)}ms"}]


def build_arguments(
    task: Any,
    api_key: Optional[str] = None,
    tokenizer_path: Optional[str] = None,
) -> dict:
    """把平台压测任务翻译成 EvalScope Arguments 的构造入参（dict）。

    Args:
        task: 具备 perf_task 字段的 ORM 对象或 dict
        api_key: 目标端点的鉴权 Key（直连模型时为模型自身的 api_key；
                 经网关时为平台 AP​I Key），由调用方解析后传入

    Returns:
        可直接传给 ``evalscope.perf.Arguments(**kwargs)`` 的字典
    """
    mode = _get(task, "mode")
    target_url = (_get(task, "target_url") or "").rstrip("/")
    if not target_url:
        raise ValueError("target_url 为空，无法构造压测参数")
    if not target_url.endswith(CHAT_COMPLETIONS_PATH):
        target_url = f"{target_url}{CHAT_COMPLETIONS_PATH}"

    args: dict[str, Any] = {
        "api": "openai",
        "url": target_url,
        "model": _get(task, "model_name_snapshot") or "",
        "dataset": _get(task, "dataset_type") or "random",
        "stream": bool(_get(task, "stream", True)),
        "temperature": float(_get(task, "temperature") or 0.0),
        # 固定随机种子，保证多次压测的负载一致
        "seed": 42,
        # 减少 EvalScope 内部 SQLite 提交次数，降低压测期间自身 I/O 干扰
        "db_commit_interval": 10000,
        # 保留 EvalScope 的连接预检（默认开启）：它能在正式压测前
        # 用一次轻量请求暴露 URL / model / 鉴权配置错误。
        # 注意 401 属于 non-retryable，预检会立刻失败并只报
        # "TimeoutError: Test connection failed"，因此调用方需自行保证 api_key 已配置。
        "no_test_connection": False,
        "outputs_dir": settings.perf_outputs_dir,
    }

    if api_key:
        args["api_key"] = api_key

    # tokenizer：random 数据集必需（EvalScope 用它按 token 精确切分输入/输出长度）。
    # 优先用调用方推导的值，其次用任务里存的。
    resolved_tokenizer = (tokenizer_path or _get(task, "tokenizer_path") or "").strip()
    if resolved_tokenizer:
        args["tokenizer_path"] = resolved_tokenizer

    # 经网关压测：强制打上压测标记，网关据此跳过请求日志写入（ADR-004）。
    # 用户无法关闭 —— 这是「不污染 Token 统计」的实现前提。
    if _get(task, "via_gateway"):
        existing = dict(args.get("headers") or {})
        existing["X-Perf-Test"] = "1"
        args["headers"] = existing

    # ---- 输入/输出长度：平台用固定值，EvalScope 用 min/max 区间，故两端取同值 ----
    input_length = _get(task, "input_length")
    output_length = _get(task, "output_length")
    if input_length:
        args["min_prompt_length"] = int(input_length)
        args["max_prompt_length"] = int(input_length)
    if output_length:
        args["min_tokens"] = int(output_length)
        args["max_tokens"] = int(output_length)

    # ---- 按模式填压力参数 ----
    if mode == "closed_loop":
        args["open_loop"] = False
        args["parallel"] = int(_get(task, "parallel") or 1)
        args["number"] = int(_get(task, "number") or 1)

    elif mode == "open_loop":
        args["open_loop"] = True
        args["rate"] = float(_get(task, "rate") or 1.0)
        args["number"] = int(_get(task, "number") or 1)
        # open_loop 下 parallel 仅作为连接池上限
        args["parallel"] = int(
            _get(task, "max_concurrency") or DEFAULT_OPEN_LOOP_CONCURRENCY
        )

    elif mode == "sla":
        metric = _get(task, "sla_metric")
        threshold = _get(task, "sla_threshold_ms")
        lower = int(_get(task, "sla_lower_bound") or 1)
        upper = int(_get(task, "sla_upper_bound") or settings.perf_max_parallel)
        if upper <= lower:
            raise ValueError(f"SLA 搜索上界 {upper} 必须大于下界 {lower}")

        args["sla_auto_tune"] = True
        args["sla_variable"] = "parallel"
        args["sla_params"] = build_sla_params(metric, int(threshold))
        args["sla_lower_bound"] = lower
        args["sla_upper_bound"] = upper
        # SLA 模式每个压力点跑一次完整压测，用 number 控制单次请求量
        args["number"] = int(_get(task, "number") or DEFAULT_SLA_NUMBER)

    elif mode == "multi_turn":
        turns = int(_get(task, "turns") or 1)
        args["multi_turn"] = True
        args["min_turns"] = turns
        args["max_turns"] = turns
        args["parallel"] = int(_get(task, "parallel") or 1)
        args["number"] = int(_get(task, "number") or 1)

    else:
        raise ValueError(f"未知的压测模式: {mode}")

    return args


# ============================================================
# 执行（子进程 + 进度/中止监控）
# ============================================================

def task_work_dir(task_id: int) -> str:
    """单个任务的 EvalScope 工作目录（隔离，避免 benchmark_data.db 冲突）。"""
    return os.path.join(settings.perf_outputs_dir, str(task_id))


def report_path_for(task_id: int) -> str:
    """EvalScope 原生 HTML 报告路径（gen_perf_html_report 写入 output_path 下）。"""
    return os.path.join(task_work_dir(task_id), f"perf_task_{task_id}", "perf_report.html")


def _sync_redis():
    """子进程监控用的同步 Redis 客户端（引擎跑在线程里，不能用 async 客户端）。"""
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _read_file_tail(path: str, limit: int = 1500) -> str:
    """读文件末尾若干字符（用于把子进程输出附在报错里）。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return ""
    return content[-limit:]


def _read_progress(work_dir: str) -> Optional[dict]:
    """读 EvalScope 写的 progress.json。

    EvalScope 不同版本的落盘位置不一样（`{outputs_dir}/progress.json` 或
    `{outputs_dir}/{task_name}/progress.json`），这里两处都找，取 mtime 最新的，
    避免因路径猜错导致"进度永远 0%"（Phase2 未验证假设 #3）。
    """
    candidates: list[str] = [os.path.join(work_dir, "progress.json")]
    try:
        for root, _dirs, files in os.walk(work_dir):
            if "progress.json" in files:
                candidates.append(os.path.join(root, "progress.json"))
    except OSError:
        pass

    newest: Optional[str] = None
    newest_mtime = -1.0
    for path in candidates:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime > newest_mtime:
            newest_mtime = mtime
            newest = path

    if newest is None:
        return None
    try:
        with open(newest, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


class EvalScopeEngine:
    """EvalScope 执行封装。

    执行模型：把参数写成 JSON → 拉起 `python -m app.tasks.perf_entry` 子进程 →
    轮询 progress.json 回写进度、轮询中止标志可 terminate → 读结果文件解析。

    选子进程而非同进程调用的原因见 app/tasks/perf_entry.py 顶部说明。
    """

    # 进度/中止轮询间隔（秒）
    poll_interval: float = 2.0

    def run(
        self,
        task: Any,
        api_key: Optional[str] = None,
        tokenizer_path: Optional[str] = None,
    ) -> dict:
        """执行压测，返回平台 result_json；失败抛异常由 runner 落状态。"""
        available, err = engine_available()
        if not available:
            raise PerfEngineUnavailable(f"压测引擎不可用：{err}")

        task_id = int(_get(task, "id"))
        work_dir = task_work_dir(task_id)
        shutil.rmtree(work_dir, ignore_errors=True)
        os.makedirs(work_dir, exist_ok=True)

        # ---- 构造 EvalScope 参数 ----
        args = build_arguments(task, api_key, tokenizer_path)
        args.update(
            {
                "outputs_dir": work_dir,
                # 固定目录名，避免 timestamp 目录导致进度/报告路径不确定
                "name": f"perf_task_{task_id}",
                "no_timestamp": True,
                # 让 EvalScope 写 progress.json（我们靠它做进度回写）
                "enable_progress_tracker": True,
            }
        )

        args_json = os.path.join(work_dir, "args.json")
        out_json = os.path.join(work_dir, "result.json")
        with open(args_json, "w", encoding="utf-8") as f:
            json.dump(args, f, ensure_ascii=False, default=str)

        # ---- 拉起子进程 ----
        # 输出重定向到 engine.log（而不是 PIPE）：
        #   * PIPE 只在进程结束时才读 → 期间完全看不到进度，用户以为卡死
        #   * 落文件后可以 `tail -f` 实时观察 EvalScope 的进度条 / tokenizer 下载 / 报错
        cmd = [sys.executable, "-m", "app.tasks.perf_entry", args_json, out_json]
        engine_log = os.path.join(work_dir, "engine.log")
        logger.info("启动压测子进程 task=%s argv=%s log=%s", task_id, cmd[2:], engine_log)
        log_fh = open(engine_log, "w", encoding="utf-8", buffering=1)  # noqa: SIM115 - 需跨轮询持有
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # ---- 监控：进度回写 + 中止 ----
        aborted = False
        redis_client = None
        try:
            redis_client = _sync_redis()
        except Exception:  # noqa: BLE001 - Redis 不可用时仍可执行，只是没进度/中止
            logger.warning("Redis 不可用，压测进度与中止功能降级", exc_info=True)

        abort_key = f"{settings.perf_redis_prefix}:abort:{task_id}"
        progress_key = f"{settings.perf_redis_prefix}:progress:{task_id}"
        deadline = time.monotonic() + settings.perf_task_timeout
        timed_out = False
        last_sample: Optional[tuple[int, float]] = None

        while proc.poll() is None:
            # 中止检查
            if redis_client is not None:
                try:
                    if redis_client.get(abort_key):
                        aborted = True
                        logger.warning("压测任务 %s 收到中止信号，终止子进程", task_id)
                        proc.terminate()
                        break
                except Exception:  # noqa: BLE001
                    pass

            # 超时保护
            if time.monotonic() > deadline:
                timed_out = True
                logger.warning("压测任务 %s 超过硬超时 %ss，终止子进程", task_id, settings.perf_task_timeout)
                proc.terminate()
                break

            # 进度回写（顺手用相邻两次采样的差值估算当前 RPS）
            snap = _read_progress(work_dir)
            if snap and redis_client is not None:
                now_ts = time.monotonic()
                sent = int(snap.get("processed_count") or 0)
                current_rps = None
                if last_sample is not None:
                    delta_sent = sent - last_sample[0]
                    delta_t = now_ts - last_sample[1]
                    if delta_t > 0 and delta_sent >= 0:
                        current_rps = round(delta_sent / delta_t, 2)
                last_sample = (sent, now_ts)
                try:
                    redis_client.set(
                        progress_key,
                        json.dumps(
                            {
                                "sent": sent,
                                "total": snap.get("total_count") or 0,
                                "percent": snap.get("percent"),
                                "current_rps": current_rps,
                                "status": snap.get("status"),
                            }
                        ),
                        ex=3600,
                    )
                except Exception:  # noqa: BLE001
                    pass

            time.sleep(self.poll_interval)

        # 收尾：等待子进程真正退出，并从 engine.log 取尾部用于报错
        stdout_tail = ""
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logger.error("压测任务 %s 子进程未在 30s 内退出，强制 kill", task_id)
            proc.kill()
            proc.wait(timeout=10)
        finally:
            try:
                log_fh.close()
            except Exception:  # noqa: BLE001
                pass
            stdout_tail = _read_file_tail(engine_log)

        # 清理进度/中止键
        if redis_client is not None:
            try:
                redis_client.delete(progress_key, abort_key)
            except Exception:  # noqa: BLE001
                pass

        if aborted:
            raise PerfAborted("压测已被用户中止")
        if timed_out:
            raise PerfRunFailed(f"压测超过硬超时 {settings.perf_task_timeout}s，已强制终止")

        # ---- 读结果 ----
        payload = self._load_result(out_json)
        if not payload.get("ok"):
            detail = payload.get("error") or "未知错误"
            tail = (stdout_tail or "")[-1500:]
            raise PerfRunFailed(f"{detail}\n--- 子进程输出(尾部) ---\n{tail}" if tail else detail)

        from app.services.perf_result_parser import parse_results

        error_db = os.path.join(work_dir, "benchmark_data.db")
        result = parse_results(
            payload.get("results"), error_db_path=error_db if os.path.exists(error_db) else None
        )

        # 记录 HTML 报告路径（存在才登记）
        rp = report_path_for(task_id)
        result["report_path"] = rp if os.path.exists(rp) else None
        result["work_dir"] = work_dir
        return result

    @staticmethod
    def _load_result(out_json: str) -> dict:
        try:
            with open(out_json, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {"ok": False, "error": "结果文件格式异常"}
        except FileNotFoundError:
            return {"ok": False, "error": "子进程未产出结果文件（可能启动即崩溃）"}
        except (OSError, ValueError) as e:
            return {"ok": False, "error": f"读取结果文件失败: {e}"}
