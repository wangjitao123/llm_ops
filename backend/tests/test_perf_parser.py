"""结果解析器测试（Phase 2）。

重点覆盖 EvalScope 返回的**两种形态**：
  1. pydantic 对象（BenchmarkSummary / PercentileResult）
  2. 已序列化 dict（key 为展示名，如 'Avg TTFT (ms)'）
因为 `run_perf_benchmark` 在不同调用路径下可能给我们其中任意一种。
"""
import pytest

from app.services.perf_result_parser import (
    parse_percentiles,
    parse_results,
    parse_summary,
    read_error_breakdown,
)


# ============================================================
# 假对象：模拟 EvalScope 的 pydantic 模型（只保留我们关心的字段）
# ============================================================

class FakeSummary:
    """模拟 BenchmarkSummary（蛇形属性名）。"""

    def __init__(self, **kw):
        self.avg_ttft = kw.get("avg_ttft", 142.0)
        self.avg_tpot = kw.get("avg_tpot", 18.6)
        self.output_token_throughput = kw.get("output_token_throughput", 1284.0)
        self.request_throughput = kw.get("request_throughput", 20.0)
        self.avg_latency = kw.get("avg_latency", 1.2)
        self.time_taken = kw.get("time_taken", 161.0)
        self.avg_input_tokens = kw.get("avg_input_tokens", 1024.0)
        self.avg_output_tokens = kw.get("avg_output_tokens", 256.0)
        self.total_requests = kw.get("total_requests", 3000)
        self.succeed_requests = kw.get("succeed_requests", 2985)


class FakeRow:
    def __init__(self, percentile, ttft, latency, tpot, output_throughput):
        self.percentile = percentile
        self.ttft = ttft
        self.latency = latency
        self.tpot = tpot
        self.output_throughput = output_throughput


class FakePercentileResult:
    def __init__(self, rows):
        self.rows = rows


def _rows():
    return [
        FakeRow("50%", 112.0, 1.2, 18.0, 1300.0),
        FakeRow("90%", 158.0, 2.4, 20.0, 1200.0),
        FakeRow("95%", 172.0, 3.1, 21.0, 1150.0),
        FakeRow("99%", 186.0, 4.8, 23.0, 1000.0),
    ]


# ============================================================
# 摘要指标
# ============================================================

def test_parse_summary_from_pydantic_object():
    m = parse_summary(FakeSummary())
    assert m["ttft_mean"] == 142.0
    assert m["tpot_mean"] == 18.6
    assert m["output_throughput"] == 1284.0
    assert m["request_throughput"] == 20.0
    assert m["avg_latency_s"] == 1.2
    assert m["total_requests"] == 3000
    assert m["success_count"] == 2985
    assert m["failed_count"] == 15


def test_parse_summary_computes_success_rate():
    m = parse_summary(FakeSummary(total_requests=1000, succeed_requests=950))
    assert m["success_rate"] == 95.0
    assert m["failed_count"] == 50


def test_parse_summary_from_dict_with_display_keys():
    """序列化后的 dict：key 是展示名（EvalScope 落盘 JSON 的形态）。"""
    raw = {
        "Avg TTFT (ms)": 142.5,
        "Avg TPOT (ms)": 18.6,
        "Output Throughput (tok/s)": 1284.0,
        "Req Throughput (req/s)": 20.0,
        "Avg Latency (s)": 1.2,
        "Test Duration (s)": 161.0,
        "Total Requests": 3000,
        "Success Requests": 3000,
    }
    m = parse_summary(raw)
    assert m["ttft_mean"] == 142.5
    assert m["output_throughput"] == 1284.0
    assert m["success_rate"] == 100.0
    assert m["failed_count"] == 0


def test_parse_summary_handles_none():
    m = parse_summary(None)
    assert m["ttft_mean"] is None
    assert m["success_rate"] is None


def test_parse_summary_tolerates_zero_total():
    m = parse_summary(FakeSummary(total_requests=0, succeed_requests=0))
    assert m["success_rate"] is None
    assert m["failed_count"] is None


# ============================================================
# 百分位
# ============================================================

def test_parse_percentiles_from_pydantic_object():
    p = parse_percentiles(FakePercentileResult(_rows()))
    assert p["labels"] == ["50%", "90%", "95%", "99%"]
    assert p["ttft"]["p50"] == 112.0
    assert p["ttft"]["p95"] == 172.0
    assert p["ttft"]["p99"] == 186.0
    assert p["ttft"]["max"] is None  # 无 100% 行
    assert p["latency"]["p99"] == 4.8
    assert p["tpot"]["p50"] == 18.0
    assert p["output_throughput"]["p99"] == 1000.0


def test_parse_percentiles_from_column_oriented_dict():
    """列式结构：{'Percentiles': [...], 'TTFT (ms)': [...]}"""
    raw = {
        "Percentiles": ["50%", "90%", "95%", "99%"],
        "TTFT (ms)": [112.0, 158.0, 172.0, 186.0],
        "Latency (s)": [1.2, 2.4, 3.1, 4.8],
        "TPOT (ms)": [18.0, 20.0, 21.0, 23.0],
        "Output (tok/s)": [1300.0, 1200.0, 1150.0, 1000.0],
    }
    p = parse_percentiles(raw)
    assert p["ttft"]["p50"] == 112.0
    assert p["ttft"]["p99"] == 186.0
    assert p["latency"]["p90"] == 2.4
    assert p["output_throughput"]["p95"] == 1150.0


def test_parse_percentiles_from_rows_dict():
    raw = {
        "rows": [
            {"percentile": "50%", "ttft": 100.0},
            {"percentile": "99%", "ttft": 200.0},
        ]
    }
    p = parse_percentiles(raw)
    assert p["ttft"]["p50"] == 100.0
    assert p["ttft"]["p99"] == 200.0
    assert p["ttft"]["p95"] is None


def test_parse_percentiles_handles_missing_percentile():
    raw = {"rows": [{"percentile": "50%", "ttft": 100.0}]}
    p = parse_percentiles(raw)
    assert p["ttft"]["p50"] == 100.0
    assert p["ttft"]["p99"] is None


def test_parse_percentiles_handles_none():
    p = parse_percentiles(None)
    assert p["labels"] == []
    assert "ttft" not in p


# ============================================================
# 错误分布（SQLite）
# ============================================================

def test_read_error_breakdown_missing_file_returns_empty():
    assert read_error_breakdown("/nonexistent/path.db") == {}


def test_read_error_breakdown_none_returns_empty():
    assert read_error_breakdown(None) == {}


def test_read_error_breakdown_reads_sqlite(tmp_path):
    import sqlite3

    db = tmp_path / "benchmark_data.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE result (success INTEGER, response_messages TEXT)"
    )
    conn.executemany(
        "INSERT INTO result VALUES (?, ?)",
        [(1, None), (1, None), (0, "429 rate limited"), (0, "429 rate limited"), (0, "504 timeout")],
    )
    conn.commit()
    conn.close()

    breakdown = read_error_breakdown(str(db))
    assert breakdown["429 rate limited"] == 2
    assert breakdown["504 timeout"] == 1


def test_read_error_breakdown_tolerates_unknown_schema(tmp_path):
    import sqlite3

    db = tmp_path / "weird.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE result (foo TEXT)")  # 没有 success/message 列
    conn.commit()
    conn.close()
    assert read_error_breakdown(str(db)) == {}


# ============================================================
# 整体解析
# ============================================================

def test_parse_results_full_shape():
    raw = {
        "parallel_200_number_2000": {
            "metrics": FakeSummary(),
            "percentiles": FakePercentileResult(_rows()),
        }
    }
    result = parse_results(raw)
    assert result["run_key"] == "parallel_200_number_2000"
    assert result["metrics"]["ttft_mean"] == 142.0
    assert result["percentiles"]["ttft"]["p99"] == 186.0
    assert result["errors"] == {}
    assert "parallel_200_number_2000" in result["all_runs"]


def test_parse_results_sla_multi_run_keeps_all_runs():
    """SLA 模式会返回多个压力点的结果，需保留每组摘要。"""
    raw = {
        "parallel_50_number_100": {"metrics": FakeSummary(avg_ttft=80.0), "percentiles": None},
        "parallel_200_number_100": {"metrics": FakeSummary(avg_ttft=180.0), "percentiles": None},
    }
    result = parse_results(raw)
    assert len(result["raw_run_keys"]) == 2
    assert result["all_runs"]["parallel_50_number_100"]["ttft_mean"] == 80.0
    assert result["all_runs"]["parallel_200_number_100"]["ttft_mean"] == 180.0


def test_parse_results_empty_returns_skeleton():
    result = parse_results({})
    assert result["run_key"] is None
    assert result["metrics"]["ttft_mean"] is None
    assert result["errors"] == {}


def test_parse_results_none_returns_skeleton():
    result = parse_results(None)
    assert result["run_key"] is None
