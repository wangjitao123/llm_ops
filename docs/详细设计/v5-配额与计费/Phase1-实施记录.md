# 配额与计费闭环 · Phase1 实施记录

日期：2026-11-18
范围：`app_key.token_quota / rpm_limit / rpd_limit` 从"只存不用"变成**真正拦截**；
新增模型计费单价；Token 统计里的费用从恒为 0 变成真实金额。

---

## 1. 背景：这些字段早就存在，但从来没生效

动手前先确认了现状，避免重复造轮子：

| 已有 | 位置 | 状态 |
|---|---|---|
| `app_key.qps_limit` | `models/key.py` | ✅ 已生效（`check_qps`） |
| `app_key.rpm_limit / rpd_limit` | 同上 | ❌ 存了、能填，**从未校验** |
| `app_key.token_quota / token_used` | 同上 | ❌ 存了、前端能填，**从未校验，`token_used` 也从不更新** |
| `token_stats_hourly/daily.total_cost` | `models/token.py` | ⚠️ 字段在，聚合时**没算，恒为 0** |
| `/api/v1/tokens/cost-report` | `api/v1/tokens.py` | ⚠️ 接口在，返回全 0 |
| 前端"总费用 (¥)"卡片、费用列 | `views/token/index.vue` | ⚠️ 已绑定 `total_cost`，只是没数 |

结论：**UI、接口、字段都齐了，缺的是"定价 → 计费 → 拦截"这条链**。所以本次是填空，不是新建模块。

---

## 2. 改动总览

```
配额（拦截）                        计费（出账）
─────────────                      ─────────────
rpm / rpd  → Redis 固定窗口         单价表 model_pricing（新表）
token_quota → app_key.token_used    小时聚合按单价算 total_cost
                                    → /tokens/cost-report + 前端费用列
```

### 2.1 配额拦截

在 `proxy.py` 的 Key 鉴权通过之后、路由解析之前加两道：

| 校验 | 依据 | 超限返回 |
|---|---|---|
| `rpm_limit` / `rpd_limit` | Redis 固定窗口计数（分钟 / 东八区自然日） | `429` + `error.type=rate_limit_error` + `Retry-After`（到下个分钟/零点） |
| `token_quota` | 已加载的 `app_key.token_used`，**不额外查库** | `429` + `error.type=insufficient_quota` |

两个判定细节：

- **`NULL` = 不限制**。存量 Key 全是 NULL，所以这次上线对它们的行为是**零变化**，
  不会出现"发版后突然开始 429"。`rate_limit_config.default_key_rpm/rpd`（6000 / 100000）
  **故意不套用**：`rpd=100000` 对 100 QPS 的调用方 17 分钟就打穿，属于会误伤业务的上限。
- 判定用 `>` 而不是 `>=`（与 QPS 一致）：`rpm_limit=600` 表示第 600 个放行、第 601 个拒绝。

`token_used` 的累计放在两处，保证"流式/非流式都扣得上"：

- 非流式：拿到 usage 后 `UPDATE app_key SET token_used = token_used + n`，与日志同一事务；
- 流式：用量只有流结束才知道，所以在 `_backfill_log_usage` 里**同时**回填日志和累加 `token_used`
  ——否则会出现"日志有 token、配额没扣"的漏洞，流式请求可以无限刷。

原子累加（`token_used = token_used + n`）而不是读改写，避免并发丢更新。
压测流量（`suppress_request_log=True`）不记账，与"压测不进报表"的既有隔离策略一致。

### 2.2 计费单价

新表 `model_pricing`，一个模型一条记录，单位统一为**「元 / 千 token」**（与 OpenAI/云厂商报价口径一致）：

```
本次费用 = 输入 token / 1000 × input_price_per_1k
         + 输出 token / 1000 × output_price_per_1k
```

金额列用 `DECIMAL(18,6)`：账单场景不能用 float，累计会越算越偏。

**为什么必须建新表**：项目没有 Alembic，启动靠 `create_all`，它只建缺失的表、
**不会给已有表加列**。若图省事往 `model` 或 `api_request_log` 加 `price` / `cost` 列，
线上库根本不会有这列，代码一跑就是 `UndefinedColumn`。（`init_db.py` 的注释里也写了这条。）

### 2.3 计费在哪个环节算

在**小时聚合**时算，写进 `token_stats_hourly.total_cost`；天聚合再 `sum` 上去：

```python
# app/tasks/stats_aggregator.py
cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1000
```

选这个位置的理由：

1. **不用改高频写路径**。每请求多算一次钱 = 多一次 join 与一次写，热路径上不划算；
2. **天然支持任意维度**。cost 对 token 是线性的，所以 `SUM` 可以直接跨模型求和，
   按 Key / 按应用聚合也是一条 SQL（不需要回表逐行算）；
3. **历史账单不会因改价而漂移**。已聚合的小时/天行是落库的固定值，
   改单价只影响之后聚合出的账单 —— 这正是财务上想要的行为。

代价：**当前小时的费用要等聚合跑完才出现**（最多约 1 小时延迟）。日汇总每小时刷新一次，
所以页面上的"今日费用"是滚动更新的，不是实时到秒。账单场景可接受。

---

## 3. 改动文件

| 文件 | 说明 |
|---|---|
| `backend/app/models/pricing.py` | **新增** `ModelPricing` |
| `backend/app/schemas/pricing.py` | **新增** 请求/响应 schema（含 `unpriced_model_ids`） |
| `backend/app/repositories/pricing_repo.py` | **新增** 查询/upsert/删除/未配价模型 |
| `backend/app/services/pricing_service.py` | **新增** Decimal→float 序列化、upsert |
| `backend/app/api/v1/pricing.py` | **新增** `GET/PUT/DELETE /api/v1/pricing` |
| `backend/app/models/__init__.py` | 注册新表（否则 `create_all` 看不到） |
| `backend/app/main.py` | 挂载 `pricing` 路由 |
| `backend/app/services/rate_limiter.py` | 新增 `check_key_windows` / `check_token_quota` / `_incr_window` |
| `backend/app/services/proxy_service.py` | 新增 `add_token_used`（原子累加） |
| `backend/app/api/v1/proxy.py` | 接入 quota 校验；流式回填时同步累加 `token_used` |
| `backend/app/tasks/stats_aggregator.py` | `_cost_expr()`，三维度写 `total_cost`，天聚合 `sum(cost)` |
| `frontend/src/api/pricingApi.ts` | **新增** 前端 API |
| `frontend/src/views/model/index.vue` | 操作列"计费"弹窗；未配价模型打 `未计费` 标签 |
| `frontend/src/views/key/index.vue` | 表单加 RPM/RPD；配额列显示 `已用 / 上限` |
| `backend/tests/test_pricing_quota.py` | **新增** 15 个用例 |
| `backend/tests/test_proxy_conn_release.py` | 补 2 个配额拦截用例；假 Key 显式给配额字段 |
| `backend/tests/test_proxy_http_client.py` | `_backfill_log_usage` 新增 `app_key_id` 形参 |

---

## 4. 验证

### 4.1 单测

```
cd backend && python -m pytest tests/ -q
# 307 passed（原 290 + 新增 17）
python -m app.tools.check_symbols      # [OK]
```

计费算术不是"打桩断言"，而是**用 SQLite 执行与生产同一段 `_cost_expr()`**：
1000 输入 + 500 输出、单价 0.004/0.012 → 断言 0.010 元；未配价模型 → 断言 0 元。

### 4.2 线上冒烟（部署后）

```sql
-- 1) 新表是否建出来（AUTO_CREATE_TABLES=false 时需手工执行 DDL，见 §5）
\d model_pricing

-- 2) 配置价格后，等一小时聚合，看费用是否非 0
SELECT stats_date, stats_hour, dimension_id, total_tokens, total_cost
FROM token_stats_hourly
WHERE dimension_type='model' ORDER BY stats_date DESC, stats_hour DESC LIMIT 10;
```

想立刻看到数（不等定时任务）：

```bash
docker compose exec api-server python -c \
  "from app.tasks.stats_aggregator import aggregate_hourly_stats as t; t(hour_offsets=[0])"
```

```bash
# 3) 配额拦截：给 Key 设 token_quota=100，然后打满
curl -s localhost:8000/v1/chat/completions -H "Authorization: Bearer $KEY" ... 
# 用尽后应返回：{"error":{"message":"token quota exhausted...","type":"insufficient_quota"}}
```

### 4.3 页面

- 模型管理 → 某模型行 → 点"计费" → 填输入/输出单价 → 保存；
  未配价的模型名称旁会出现橙色 `未计费` 标签。
- Key 管理 → 新建/编辑 Key → 多了 RPM / RPD 两个输入框（留空 = 不限）；
  列表"Token 配额"列显示 `已用 / 上限`。
- Token 统计 → "总费用 (¥)" 与费用列，配价后不再是 0。

---

## 5. 生产注意

0. **聚合跑在 `celery-worker` 里，不在 api-server**。费用是 Celery 任务算的，所以
   「只重建 api-server」会导致：页面能配价、统计表有新行、但 `total_cost` 恒为 0。
   部署时 `api-server` / `web` / `celery-worker` / `celery-beat` 四个服务必须一起重建。
   （2026-11-18 首版部署文档漏了这条，已在部署包文档中修正。）

1. **表要建出来**。`deploy/docker-compose.yml` 默认 `AUTO_CREATE_TABLES=true`，
   启动即建；若线上关了自动建表，先手工执行：

```sql
CREATE TABLE IF NOT EXISTS model_pricing (
    id BIGSERIAL PRIMARY KEY,
    model_id BIGINT NOT NULL UNIQUE REFERENCES model(id),
    input_price_per_1k NUMERIC(18,6) DEFAULT 0,
    output_price_per_1k NUMERIC(18,6) DEFAULT 0,
    currency VARCHAR(8) DEFAULT 'CNY',
    remark VARCHAR(200),
    created_by VARCHAR(64),
    updated_by VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

2. **上线顺序无强依赖**：不配价格 = 计 0 元（与现在一致）；不设配额 = 不限制（与现在一致）。
   所以可以先发版、再慢慢配，不会因为"没填价格"而报错或拦流量。

3. **改价不追溯**：历史小时的 `total_cost` 是落库快照，改单价不会改写它们。
   如果业务上需要"按新价重算历史"，得手工重跑聚合（`aggregate_hourly_stats(hour_offsets=[...])`），
   这会用**当前**单价覆盖旧快照 —— 重跑前想清楚。

4. **`token_used` 是唯一的配额依据**。如果哪天手工清空或回滚了 `api_request_log`，
   记得同步 `app_key.token_used`，否则配额判定会与实际用量脱节。
   校准 SQL：
   ```sql
   UPDATE app_key k SET token_used = COALESCE((
     SELECT SUM(l.total_tokens) FROM api_request_log l WHERE l.app_key_id = k.id
   ), 0);
   ```

---

## 6. 已知限制 / 后续可做

- **计费有最长约 1 小时的聚合延迟**（见 §2.3）。要实时费用，得改成每请求写一张
  `billing_record`（价格快照），代价是热路径多一次写。当前业务量下不值得。
- **`rpm/rpd` 只认 Key 显式配置**，`rate_limit_config.default_key_rpm/rpd` 未启用（见 §2.1）。
  要让默认值生效，需要产品先确认一个不会误伤业务的数值。
- **没有余额/充值/结算单据**。现在是"用量账单"，不是"预付费扣费"。要做预付费，
  下一步是在 `app_key` 或 `application` 上加 `balance`，并在计费时扣减 + 余额不足拦截。
- **计价只支持单一币种与单档价**（无阶梯价、无缓存命中价、无输入长度分档）。
  云厂商的复杂报价模型需要扩 `model_pricing` 为"价格规则表"。