#!/usr/bin/env python
"""网关并发压测脚本 —— 验证「转一下」在高并发下会不会卡。

用法（在 backend 目录下，或改 --url 指向你的网关地址）：

    # 流式，200 并发，每并发 5 个请求
    python scripts/stress_gateway.py --key sk-xxx --model qwen2.5-7b-gptq \\
        --concurrency 200 --requests 5

    # 非流式对比
    python scripts/stress_gateway.py --key sk-xxx --model qwen2.5-7b-gptq \\
        --concurrency 200 --requests 5 --no-stream

重点关注两个数：
  * connect_error / 5xx 数量 —— 改造前在 100 并发附近会出现
    "too many clients already"（Postgres 连接打满），表现为大量 500；
  * TTFT（首 token 时间）P99 —— 反映网关自身开销是否随并发放大。

压测时另开一个终端观察数据库连接数：
    psql -c "select count(*) from pg_stat_activity where datname='ai_platform';"
    改造前：连接数 ≈ 并发流数量，且长时间不释放
    改造后：连接数稳定在连接池上限附近，流期间即归还
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class Stats:
    ok: int = 0
    failed: int = 0
    status_errors: dict[int, int] = field(default_factory=dict)
    connect_errors: int = 0
    ttft_ms: list[float] = field(default_factory=list)
    total_ms: list[float] = field(default_factory=list)

    def record_status(self, code: int) -> None:
        if 200 <= code < 300:
            self.ok += 1
        else:
            self.failed += 1
            self.status_errors[code] = self.status_errors.get(code, 0) + 1


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[k]


async def one_request(client: httpx.AsyncClient, args, stats: Stats) -> None:
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "max_tokens": args.max_tokens,
        "stream": args.stream,
    }
    headers = {"Authorization": f"Bearer {args.key}", "Content-Type": "application/json"}
    url = f"{args.url.rstrip('/')}/v1/chat/completions"

    t0 = time.perf_counter()
    first_byte: float | None = None
    try:
        if args.stream:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code < 200 or resp.status_code >= 300:
                    await resp.aread()
                    stats.record_status(resp.status_code)
                    return
                async for _chunk in resp.aiter_bytes():
                    if first_byte is None:
                        first_byte = time.perf_counter()
        else:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code < 200 or resp.status_code >= 300:
                stats.record_status(resp.status_code)
                return
            first_byte = time.perf_counter()
        stats.record_status(200)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError):
        stats.connect_errors += 1
        stats.failed += 1
        return
    finally:
        total = (time.perf_counter() - t0) * 1000.0
        if first_byte is not None:
            stats.ttft_ms.append((first_byte - t0) * 1000.0)
            stats.total_ms.append(total)


async def worker(worker_id: int, args, stats: Stats) -> None:
    limits = httpx.Limits(
        max_connections=args.conns_per_worker,
        max_keepalive_connections=args.conns_per_worker,
    )
    timeout = httpx.Timeout(args.timeout, connect=args.connect_timeout)
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        for _ in range(args.requests):
            await one_request(client, args, stats)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="网关并发压测（验证高并发是否被平台拖慢）")
    p.add_argument("--url", default="http://127.0.0.1:8000", help="平台地址（不含 /v1）")
    p.add_argument("--key", required=True, help="平台分配的 API Key（sk-...）")
    p.add_argument("--model", required=True, help="模型名（与平台模型管理一致）")
    p.add_argument("--concurrency", type=int, default=100, help="并发数")
    p.add_argument("--requests", type=int, default=5, help="每个并发发多少个请求")
    p.add_argument("--stream", dest="stream", action="store_true", default=True, help="流式（默认）")
    p.add_argument("--no-stream", dest="stream", action="store_false", help="非流式")
    p.add_argument("--prompt", default="用一句话介绍你自己", help="测试 prompt")
    p.add_argument("--max-tokens", type=int, default=64, help="限制输出长度，控制单请求耗时")
    p.add_argument("--timeout", type=float, default=120.0, help="单请求总超时（秒）")
    p.add_argument("--connect-timeout", type=float, default=10.0, help="连接超时（秒）")
    p.add_argument("--conns-per-worker", type=int, default=4, help="每个并发worker的客户端连接数")
    return p


async def main() -> int:
    args = build_parser().parse_args()
    stats = Stats()
    total_requests = args.concurrency * args.requests

    print(f"目标        : {args.url}")
    print(f"模型        : {args.model}")
    print(f"模式        : {'流式 SSE' if args.stream else '非流式'}")
    print(f"并发 / 总量 : {args.concurrency} / {total_requests}")
    print("-" * 60)

    t0 = time.perf_counter()
    await asyncio.gather(*(worker(i, args, stats) for i in range(args.concurrency)))
    elapsed = time.perf_counter() - t0

    print(f"耗时        : {elapsed:.2f}s")
    print(f"成功        : {stats.ok}")
    print(f"失败        : {stats.failed}")
    if stats.connect_errors:
        print(f"  连接/超时 : {stats.connect_errors}")
    for code, n in sorted(stats.status_errors.items()):
        hint = ""
        if code == 500:
            hint = "  ← 疑似 too many DB clients / 上游异常"
        elif code == 429:
            hint = "  ← 被限流（调大 Key/全局 QPS 再测）"
        elif code == 401:
            hint = "  ← Key 无效"
        elif code == 404:
            hint = "  ← 模型名不对或模型不在线"
        print(f"  HTTP {code}  : {n}{hint}")
    print(f"吞吐        : {stats.ok / elapsed:.1f} req/s" if elapsed > 0 else "")

    if stats.ttft_ms:
        print("-" * 60)
        print("首字节 (TTFT, ms)  P50 / P95 / P99 / max")
        print(
            f"                  {_pct(stats.ttft_ms, 50):.0f} / "
            f"{_pct(stats.ttft_ms, 95):.0f} / "
            f"{_pct(stats.ttft_ms, 99):.0f} / "
            f"{max(stats.ttft_ms):.0f}"
        )
        print(
            f"完整请求 (ms)     P50 / P95 / P99 / max\n"
            f"                  {_pct(stats.total_ms, 50):.0f} / "
            f"{_pct(stats.total_ms, 95):.0f} / "
            f"{_pct(stats.total_ms, 99):.0f} / "
            f"{max(stats.total_ms):.0f}"
        )
        mean = statistics.fmean(stats.ttft_ms)
        print(f"TTFT 均值         : {mean:.0f} ms")

    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
