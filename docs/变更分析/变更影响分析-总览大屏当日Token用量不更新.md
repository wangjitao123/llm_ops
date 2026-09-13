# 变更影响分析报告：总览大屏「今日/最新一天 Token 用量不更新」

- 项目：大模型监测管理平台
- 变更类型：fix（修复当天 Token 用量在当天内不更新的问题）
- 日期：2026-09-10
- 状态：待评审确认

---

## 1. 需求/问题描述

总览大屏的「Token 用量趋势」（7/30 天）与「今日 Token / 今日请求量」卡片，**当天内看不到当天的数据**；
但昨天及更早的历史数据正常存在。即：**只差"当天"这一块不更新，聚合链路本身没有断**。

## 2. 根因定位（代码证据）

统计数据由 **Celery Beat 定时任务**批量聚合，链路如下：

```
① 网关请求 → api_request_log        （proxy.py record_request() 同步写，实时）
② token_stats_hourly                （每小时 x:05 aggregate_hourly_stats，聚合"上一完整自然小时"）
③ token_stats_daily                 （每天 00:10 aggregate_daily_stats，从 hourly 滚动近 7 天）
④ 大屏/Tok 统计页查询 daily 粒度     （GET /v1/tokens/stats?granularity=daily → 查 token_stats_daily）
```

关键代码：

| 文件 | 现状 |
|---|---|
| `backend/app/tasks/worker.py` | `aggregate-daily-stats` 调度为 `crontab(hour=0, minute=10)` —— **每天只跑一次 00:10** |
| `backend/app/tasks/stats_aggregator.py` | `_aggregate_daily()` 每次只重算「今天+近6天」；00:10 运行时"今天"尚无小时数据，故当天无行；**当天其余时间不再刷新 token_stats_daily** |
| `frontend/src/views/dashboard/index.vue` | 今日卡片与 7/30 天趋势全部按 `granularity='daily'` 查今天区间 |

结论：**当天（今天）白天的 Token 用量已进入 token_stats_hourly，但不会滚动进 token_stats_daily，
要等次日 00:10 才会补齐 → 大屏当天看到 0 / 空，属"天然延迟"设计缺陷，非基础设施故障。**

> 佐证：用户反馈"昨天以前的数还在、只是今天/最新一天不更新"——说明 hourly/daily 历史链路正常，唯一缺口是"当天内不刷新 daily"。

## 3. 影响分析

### 3.1 数据模型 / 数据库
- 无表结构变更、无 DDL、无数据迁移。
- token_stats_hourly / token_stats_daily 均无唯一约束；同日并发重算存在重复行风险（见 5.2）。

### 3.2 后端代码
| 文件 | 改动 |
|---|---|
| `backend/app/tasks/stats_aggregator.py` | `_aggregate_daily` / `aggregate_daily_stats` 增加 `days` 参数（默认 7，语义保持"含今天共 N 天"）；仅参数化，逻辑不变 |
| `backend/app/tasks/worker.py` | beat_schedule：保留每天 00:10 全量近7天重算；**新增每小时对"当天"单独刷新**（避让 00:10，用 hour=1-23） |

### 3.3 接口（API）
- 无接口变更、无契约变化、完全向后兼容。

### 3.4 前端
- **无改动**。修复后 `/v1/tokens/stats?granularity=daily&start=今天&end=今天` 当天内即可返回数据，
  大屏「今日 Token/请求量」与趋势图"最后一天"柱自动恢复；M03-01 Token 统计页（按天粒度）同样受益。

### 3.5 定时任务 / 运维
- 调度在 `celery_app.conf.beat_schedule`（进程内调度，非 DB 调度），**重启 celery-beat 即自动生效**。
- 部署需 rebuild + restart celery-worker / celery-beat 镜像（代码变更）。

## 4. 变更方案（推荐）

1. `stats_aggregator.py`
   - `aggregate_daily_stats(days: int = 7)` / `_aggregate_daily(days: int = 7)`：`range(days)` 覆盖
     `today, today-1, …, today-(days-1)`；`days=7` 与旧行为逐字节一致（幂等：先删当天再重算）。
2. `worker.py` beat_schedule
   - 保留 `aggregate-daily-stats`：`crontab(hour=0, minute=10)` + `args=[7]`（每天凌晨兜底重算近 7 天，含晚到的小时数据）。
   - 新增 `refresh-today-stats`：`crontab(hour="1-23", minute=10)` + `args=[1]`（每小时只把"当天"从 hourly 滚到 daily）。
     - 之所以不放在 minute=0 的 0 点后重合时刻：避免与 00:10 全量任务并发删插同一天导致重复行。
     - 每小时 x:10 紧跟 x:05 的小时聚合 → "今日"延迟 ≤ ~1 小时（与数据本身小时粒度一致）。
3. 新增单测 `backend/tests/test_stats_aggregator.py`：mock `async_session`，验证
   `days` 参数控制重算天数（默认 7、刷新用 1）、幂等删除顺序与日期范围正确。

**备选方案（不推荐，供对比）**
- A. 每天 00:10 前把 hourly 全部算完再滚 → 当天内仍无数据，不解决问题。
- B. 前端当天改查 hourly 粒度实时求和 → 前后端都要改、口径两套、易不一致，改动大。
- C. 缩短刷新周期到每 10 分钟 → 今日数据更"准实时"，但每小时聚合粒度下多算无意义，徒增负载；如确需分钟级再议。

## 5. 风险与对策

| 风险 | 说明 | 对策 |
|---|---|---|
| 并发重复行 | 同日两个任务并发"先删后插"可能各插一次 → daily 重复计 | 刷新任务避开 00:10（hour=1-23）；两任务事务内原子删插 |
| 今日预警行为变化 | 用量预警(daily_token)原当天恒 0、基本不触发；修复后当天累计超阈值即触发 | 属**正向**修正（当天累计用量达到阈值即预警），评审确认即可 |
| 补数覆盖 | 只刷新当天；历史晚到小时由每天 00:10 的 7 天重算兜底 | 保持 00:10 全量任务 |
| 负载 | daily 行量级极小（数据字典：日增 ~100 行 ×7 天），每小时刷当天无压力 | 无需额外优化 |

## 6. 回归范围

- 后端：`python -m pytest tests`（含新增 stats_aggregator 测试）。
- 前端：无代码变更，仅验证大屏当日卡片/趋势在有当天 daily 行后正常显示（联调时人工确认）。
- 手动补数入口（现状支持，未改动）：`celery call aggregate_hourly_stats` 传 `hour_offsets/days_back`；`aggregate_daily_stats` 现支持 `days` 参数手动跑任意天数。
