"""EvalScope 压测结果解析器。

把 EvalScope 返回的 `(metrics, percentiles, trace_summary, workload_throughput)`
转成平台统一的 `result_json` 契约。

**两种情况都要处理**（实测 evalscope 源码 `perf/utils/perf_models.py`）：
  1. pydantic 对象：`BenchmarkSummary` / `PercentileResult`
     —— 字段是蛇形名（avg_ttft / succeed_requests / rows[].ttft）
  2. 已序列化的 dict：key 是展示名（'Avg TTFT (ms)' / 'Success Requests'）

EvalScope 的字段名 → 平台契约字段：

| EvalScope | 平台 result_json.metrics |
|-----------|--------------------------|
| avg_ttft（'Avg TTFT (ms)'） | ttft_mean |
| avg_tpot（'Avg TPOT (ms)'） | tpot_mean |
| output_token_throughput | output_throughput |
| request_throughput | request_throughput |
| succeed_requests / total_requests | success_count / total_requests / success_rate |
| avg_latency（秒） | avg_latency_s |
| time_taken | duration_s |
"""
import logging
import sqlite3
from typing import Any, Optional

logger = logging.getLogger(__name__)

# EvalScope 百分位行的标签形式（'50%' / '90%' ...）
_PCT_KEYS = {"p50": "50%", "p90": "90%", "p95": "95%", "p99": "99%", "max": "100%"}

# 平台关心的百分位列（EvalScope PercentileRow 属性名 / dict 展示名）
_PCT_COLUMNS = {
    "ttft": ("ttft", "TTFT (ms)"),
    "latency": ("latency", "Latency (s)"),
    "tpot": ("tpot", "TPOT (ms)"),
    "output_throughput": ("output_throughput", "Output (tok/s)"),
}

# 摘要指标：EvalScope 蛇形名 / dict 展示名
_SUMMARY_FIELDS = {
    "ttft_mean": ("avg_ttft", "Avg TTFT (ms)"),
    "tpot_mean": ("avg_tpot", "Avg TPOT (ms)"),
    "output_throughput": ("output_token_throughput", "Output Throughput (tok/s)"),
    "request_throughput": ("request_throughput", "Req Throughput (req/s)"),
    "avg_latency_s": ("avg_latency", "Avg Latency (s)"),
    "duration_s": ("time_taken", "Test Duration (s)"),
    "avg_input_tokens": ("avg_input_tokens", "Avg Input Tokens"),
    "avg_output_tokens": ("avg_output_tokens", "Avg Output Tokens"),
    "total_requests": ("total_requests", "Total Requests"),
    "success_count": ("succeed_requests", "Success Requests"),
}


def _is_pydantic(obj: Any) -> bool:
    return hasattr(obj, "model_dump") and not isinstance(obj, dict)


def _pick(obj: Any, snake: str, alias: str, default=None):
    """从 pydantic 对象或 dict 里取值（两种 key 风格都试）。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        if alias in obj:
            return obj[alias]
        if snake in obj:
            return obj[snake]
        return default
    # pydantic 对象
    value = getattr(obj, snake, None)
    return default if value is None else value


def _round(value: Any, digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def parse_summary(metrics_raw: Any) -> dict:
    """解析摘要指标。"""
    out: dict[str, Any] = {}
    for target, (snake, alias) in _SUMMARY_FIELDS.items():
        out[target] = _round(_pick(metrics_raw, snake, alias))

    total = out.get("total_requests")
    success = out.get("success_count")
    if total and success is not None:
        out["success_rate"] = _round(float(success) / float(total) * 100.0)
        out["failed_count"] = int(total) - int(success)
    else:
        out["success_rate"] = None
        out["failed_count"] = None

    # 计数类保持整数语义
    for key in ("total_requests", "success_count"):
        if out.get(key) is not None:
            out[key] = int(out[key])
    return out


def _extract_rows(percentiles_raw: Any) -> Optional[list]:
    """从多种形态里取出百分位行列表。

    支持：pydantic 对象（.rows）/ {'rows': [...]} / 裸 list。
    故意不依赖 `model_dump` 判断，duck-typing 更稳。
    """
    if percentiles_raw is None:
        return None
    if isinstance(percentiles_raw, list):
        return percentiles_raw
    if isinstance(percentiles_raw, dict):
        rows = percentiles_raw.get("rows")
        return rows if isinstance(rows, list) else None
    rows = getattr(percentiles_raw, "rows", None)
    return rows if isinstance(rows, list) else None


def parse_percentiles(percentiles_raw: Any) -> dict:
    """解析百分位表。

    输出：
        {
          "labels": ["50%","90%","95%","99%"],
          "ttft": {"p50":..., "p90":..., "p95":..., "p99":..., "max":...},
          "latency": {...}, "tpot": {...}, "output_throughput": {...}
        }
    """
    result: dict[str, Any] = {"labels": []}
    if percentiles_raw is None:
        return result

    # 列式结构：{'Percentiles': [...], 'TTFT (ms)': [...]} —— EvalScope 落盘 JSON 形态
    if isinstance(percentiles_raw, dict) and "Percentiles" in percentiles_raw:
        return _parse_percentiles_columns(percentiles_raw)

    rows = _extract_rows(percentiles_raw)
    if not rows:
        return result

    labels: list[str] = []
    series: dict[str, list[Optional[float]]] = {k: [] for k in _PCT_COLUMNS}
    for row in rows:
        label = _pick(row, "percentile", "Percentiles", "")
        labels.append(str(label))
        for name, (snake, alias) in _PCT_COLUMNS.items():
            series[name].append(_round(_pick(row, snake, alias)))

    result["labels"] = labels
    for name, values in series.items():
        result[name] = _map_labels_to_slots(labels, values)
    return result


def _parse_percentiles_columns(raw: dict) -> dict:
    """解析列式的百分位结构。"""
    labels = [str(x) for x in (raw.get("Percentiles") or [])]
    result: dict[str, Any] = {"labels": labels}
    for name, (_snake, alias) in _PCT_COLUMNS.items():
        column = raw.get(alias) or []
        values = [_round(v) for v in column] if isinstance(column, list) else []
        result[name] = _map_labels_to_slots(labels, values)
    return result


def _map_labels_to_slots(labels: list[str], values: list[Optional[float]]) -> dict:
    """把 ['50%','90%',...] 映射成 {'p50':..., 'p99':...}。"""
    index = {label: i for i, label in enumerate(labels)}
    slots: dict[str, Optional[float]] = {}
    for slot, label in _PCT_KEYS.items():
        i = index.get(label)
        slots[slot] = values[i] if i is not None and i < len(values) else None
    return slots


def read_error_breakdown(db_path: Optional[str], limit: int = 20) -> dict[str, int]:
    """从 EvalScope 的结果 SQLite 读取失败请求的错误分布。

    实现上**不硬编码列名**（用 PRAGMA 自省），因为上游列名常量可能变化；
    任何异常都返回空 dict，绝不影响主流程。
    """
    if not db_path:
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
    except Exception:
        logger.debug("打开结果库失败: %s", db_path, exc_info=True)
        return {}

    try:
        cols = [r[1].lower() for r in conn.execute("PRAGMA table_info(result)")]
        if not cols:
            return {}
        success_col = next((c for c in cols if c in ("success", "is_success")), None)
        msg_col = next(
            (c for c in cols if "response" in c or "message" in c or "error" in c), None
        )
        if success_col is None or msg_col is None:
            return {}

        rows = conn.execute(
            f"SELECT {msg_col}, COUNT(*) AS cnt FROM result "
            f"WHERE {success_col} = 0 GROUP BY {msg_col} ORDER BY cnt DESC LIMIT {int(limit)}"
        ).fetchall()
    except Exception:
        logger.debug("读取错误分布失败", exc_info=True)
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    breakdown: dict[str, int] = {}
    for message, count in rows:
        key = (str(message) if message is not None else "unknown").strip()[:120] or "unknown"
        breakdown[key] = int(count)
    return breakdown


def parse_results(results: Any, error_db_path: Optional[str] = None) -> dict:
    """把 `run_perf_benchmark()` 的返回值解析成平台 `result_json`。

    Args:
        results: `{run_key: {metrics, percentiles, trace_summary, workload_throughput}}`
        error_db_path: EvalScope 结果 SQLite 路径（可选，用于错误分布）

    Returns:
        平台 result_json 契约
    """
    if not isinstance(results, dict) or not results:
        return {
            "run_key": None,
            "metrics": parse_summary(None),
            "percentiles": parse_percentiles(None),
            "errors": {},
            "raw_run_keys": [],
        }

    # 多组结果（并行/速率扫描）时取第一组作为主指标，全部 run_key 都保留
    run_keys = list(results.keys())
    primary_key = run_keys[0]
    primary = results.get(primary_key) or {}

    metrics = parse_summary(primary.get("metrics"))
    percentiles = parse_percentiles(primary.get("percentiles"))

    return {
        "run_key": primary_key,
        "raw_run_keys": run_keys,
        "metrics": metrics,
        "percentiles": percentiles,
        "errors": read_error_breakdown(error_db_path),
        # 多组结果时把每组摘要都带上，便于 SLA 模式展示各压力点
        "all_runs": {
            key: parse_summary((results.get(key) or {}).get("metrics")) for key in run_keys
        },
    }
