# 变更影响分析报告：SSE 流式请求 Token 用量未统计

- 项目：大模型监测管理平台
- 变更类型：fix（修复流式/SSE 请求 Token 用量恒为 0，无法统计）
- 日期：2026-09-08
- 状态：待评审确认

---

## 1. 问题/需求描述

总览大屏与 Token 统计页只统计到"非流式"请求的用量；**凡 `stream:true`（SSE 流式）的请求，请求数有记录但 token 恒为 0**。
要求：流式请求也要统计到真实 Token 用量。

## 2. 根因定位（代码 + 线上数据证据）

线上 `api_request_log` 实证：08:17 前的非流式请求有 token（19736/79/70）；08:42 之后（上线 SSE 流式透传后）请求全部
`total_tokens=0`——即**记录源头就是 0，与定时聚合无关**。

代码证据（`backend/app/api/v1/proxy.py`，流式分支）：

| 现状 | 问题 |
|---|---|
| 流式转发 `svc.open_stream(model, body)` 后**直接** `StreamingResponse(upstream.aiter_bytes(), ...)` 纯透传 | 服务端从未读取 SSE 内容，无法拿到用量 |
| 流式分支 `record_request(...)` **不传 token 参数** → 恒 0 | 只在非流式分支解析 `upstream.json()` 的 usage |
| 转发请求体未注入 `stream_options.include_usage` | OpenAI 兼容上游（OpenAI/DeepSeek/vLLM 等）**流式响应默认不返回 usage**，即使解析也拿不到 |

## 3. 变更方案（推荐）

| 文件 | 改动 |
|---|---|
| `backend/app/services/proxy_service.py` | `record_request()` 改为**返回已 flush 的日志对象**（调用方按需取 `log.id`；现有调用方忽略返回值，向后兼容） |
| `backend/app/api/v1/proxy.py` | ① 流式请求若缺省 `stream_options.include_usage`，转发前注入 `true`（仅当上游 4xx 非 SSE 拒绝时，用原请求体重试一次兜底兼容）；<br>② 新增 SSE 透传生成器：逐字节**原样转发**给客户端，同时旁路解析 `data:` 事件的 `usage`（最后一条生效）；<br>③ 流正常结束后，用独立 DB 会话把真实 token **回填**到起始时已记录的日志行（先记 0-token 行 → 请求断开/失败也不丢请求数）；<br>④ 补记上游 4xx/5xx 错误请求日志（原先漏记） |
| 测试 | `tests/test_proxy_sse.py`：usage 解析、include_usage 注入、透传+回填；并更新 `test_proxy.py` 中 record_request 断言 |

**不改**：数据模型/数据库、`token_stats_*` 聚合链路、定时调度、前端、API 契约。

## 4. 影响分析

- 数据模型/数据库：无 DDL。
- API 行为：对客户端**完全透传透明**（字节不重编码、不改事件、不缓存全流）；仅额外注入 `stream_options`（标准 OpenAI 兼容字段，上游不认时自动回退重试一次）。
- 失败/断开场景：客户端中途断开 → 保留 0-token 行（请求数照常计入，只是无用量）；正常结束 → 回填真实用量。聚合任务照常每小时/每天运行，无需改调度。
- 性能：解析为线性旁路（逐行扫），不缓存完整流；多一路独立短事务回填。
- 兼容性风险：注入 `stream_options` 被个别上游拒绝 → 已内置"原请求体重试"兜底。

## 5. 回归范围

- 全量 `python -m pytest tests`（预计 72 + 新增用例）。
- 上线后人工验证：任意 `stream:true` 调用一次，查 `api_request_log` 最新行 total_tokens > 0；非流式不受影响。
