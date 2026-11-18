# Phase 3 实施记录 — 压测流量标记与统计隔离

> 对应 ADR-004 / M04。改动很小，但契约必须严格。

## 改动清单

| 文件 | 改动 |
|------|------|
| `backend/app/api/v1/proxy.py` | 新增 `_is_perf_test_request()`；入口处识别头并传给 `ProxyService` |
| `backend/app/services/proxy_service.py` | `ProxyService(db, suppress_request_log=False)`；`record_request()` 命中抑制时直接返回 `None` |
| `backend/app/services/perf_engine.py` | `build_arguments()` 在 `via_gateway=True` 时注入 `X-Perf-Test: 1` |
| `backend/tests/test_perf_traffic.py` | 20 个测试 |

## 契约（不可放宽）

| 维度 | 受 `X-Perf-Test` 影响？ |
|------|------------------------|
| API Key 鉴权 | ❌ 照常（无效 Key 依旧 401） |
| **速率限制** | ❌ **照常计数** |
| 路由选择 | ❌ 照常 |
| 请求转发 | ❌ 照常 |
| `api_request_log` 写入 | ✅ **跳过** |
| 流式 usage 回填 | ✅ 跳过（因 log_id 为 None） |
| 模型心跳 / 状态 | ❌ 照常 |

**为什么要保留限流计数**：如果该头能豁免限流，任何人都能伪造它拿到无限配额。
现在伪造它最多让自己的请求不进报表 —— 没有收益动机，损失可控。

## 实现方式：为什么改 Service 而不是 7 处调用点

`chat_completions` 里有 7 处 `record_request()` 调用（流式 504/502/4xx/正常、非流式 504/502/正常）。
逐处加 `if not is_perf_test` 会产生 7 处重复分支，且容易漏改。

改为**请求级标记 + 单点抑制**：

```python
# proxy.py 入口
is_perf_test = _is_perf_test_request(request.headers)
svc = ProxyService(db, suppress_request_log=is_perf_test)

# proxy_service.py
async def record_request(...) -> Optional[ApiRequestLog]:
    if self.suppress_request_log:
        return None
    ...
```

`ProxyService` 本身就是**每请求一个实例**，所以这个标记天然是请求作用域的，不引入全局状态。

流式路径连带生效：`log = await svc.record_request(...)` 得到 `None` →
`log_id = log.id if log else None` → `_relay_sse_stream(upstream, None)` →
`_backfill_log_usage(None, usage)` 在 `if not log_id` 处提前返回。**无需额外改动**。

## 头部识别规则

```python
_PERF_TEST_TRUTHY = ("1", "true")
# 仅精确匹配（大小写/首尾空白不敏感）
```

刻意**不接受** `yes` / `on` / `2` 等值 —— 避免客户端随手传个"看起来像真"的值就把自己排除出统计。

## 注入侧

`build_arguments()` 里：

```python
if _get(task, "via_gateway"):
    existing = dict(args.get("headers") or {})
    existing["X-Perf-Test"] = "1"
    args["headers"] = existing
```

依据：EvalScope `Arguments.headers: Dict[str, Any]`（"Custom headers"，`perf/arguments.py:85`）。

**只在 `via_gateway=True` 时注入** —— 直连模型根本不经过网关，打标无意义。

## 待实测验证

| # | 假设 | 错了会怎样 |
|---|------|-----------|
| 1 | EvalScope 会把 `Arguments.headers` 真的带到每个 HTTP 请求上 | 经网关压测的流量会正常进统计（污染报表） |
| 2 | `Arguments.headers` 的 `field_validator` 经过 `secretize_auth_headers` 后仍能正常发出 | 头上不去 |

验证方法：起一次经网关的小压测（并发 1、请求 5），然后查：

```sql
-- 压测期间不应有新增行
SELECT count(*) FROM api_request_log WHERE created_at > now() - interval '5 minutes';
```

同时确认任务里 `via_gateway=true` 且 `target_url` 指向平台网关。
