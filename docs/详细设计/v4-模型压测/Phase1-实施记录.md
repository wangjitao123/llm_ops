# Phase 1 实施记录 — 模型压测后端参数层

> 记录实现过程中**与设计文档不一致**的地方，以及原因。设计文档已同步修正。

## 交付内容

| 文件 | 说明 |
|------|------|
| `backend/app/models/perf.py` | `PerfTask` / `PerfTaskLog` ORM |
| `backend/app/schemas/perf.py` | 创建/响应/对比 Schema + 按模式校验 |
| `backend/app/services/perf_fingerprint.py` | 参数指纹 + 差异字段（纯函数） |
| `backend/app/services/perf_engine.py` | **平台参数 → EvalScope Arguments 翻译层** |
| `backend/app/services/perf_service.py` | 任务 CRUD / 校验 / 对比 / 派发 |
| `backend/app/repositories/perf_repo.py` | 数据访问 + 统计聚合 |
| `backend/app/api/v1/perf.py` | REST 端点 |
| `backend/app/tasks/perf_runner.py` | Celery 任务骨架（引擎调用为 Phase 2） |
| `backend/tests/test_perf.py` | 52 个单测 |

## 偏差 1：SLA 参数从「起始并发 + 步长」改为「搜索下界 + 上界」

**原设计**（原型 v1 / PRD v1.0 / DDL）：`sla_start_parallel` + `sla_step`

**实际 EvalScope 能力**（读 `evalscope/perf/arguments.py` + `sla/sla_run.py`）：
```python
sla_auto_tune: bool = False
sla_variable: str = 'parallel'
sla_params: Optional[List[Dict[str, Any]]] = None
sla_lower_bound: int = 1
sla_upper_bound: int = 65536
sla_num_runs: int = 3
```
`parse_sla_params()` 显示 `sla_params` 是 `[{"p99_ttft": "<= 500ms"}]` 形式的列表，
压力值在 `[sla_lower_bound, sla_upper_bound]` 区间内**搜索**，**没有"步长"概念**。

**决定**：模型/DDL/PRD/功能点清单/原型统一改为 `sla_lower_bound` + `sla_upper_bound`。
不硬造 step 字段（造了也用不上，会误导用户）。

**影响**：SLA 模式的 UI 参数少一个，用户心智更简单（填区间而非步进策略）。

## 偏差 2：新增 `api_key` 解析规则（原设计未覆盖）

原设计只说"复用模型的 api_base_url / api_key"，但没区分**直连**与**经网关**两种打法下 Key 的来源不同：

| 打法 | Key 来源 | 说明 |
|------|----------|------|
| 直连模型 | `model.api_key_encrypted` | 平台向上游发请求时用的那个 Key（我们部署的 vLLM 有 `--api-key`） |
| 经网关 | `settings.perf_gateway_api_key` | **必须另配一个平台 AppKey**，否则网关会 401 |

新增配置 `PERF_GATEWAY_API_KEY`。未配置时，经网关压测会在执行阶段失败并给出明确提示。

> 这是设计阶段遗漏的一个真实缺口 —— 模型的 `api_key_encrypted` 是"平台→上游"的 Key，
> 不能拿去调平台自己的网关。

## 偏差 3：`random` 数据集用 min=max 而非区间

EvalScope 的 `min_prompt_length` / `max_prompt_length` 是**区间**，落在区间内随机取值。
平台压测需要**可控且可复现的负载**，所以 `input_length` 同时写入 min 和 max（输出长度同理）。

副作用：失去"混合长度"的压测能力。如需该能力，后续可加"长度抖动范围"参数。

## 其他实现细节

| 项 | 实现 |
|----|------|
| `seed=42` 固定 | 保证多次压测负载一致 |
| `db_commit_interval=10000` | 降低 EvalScope 内部 SQLite 提交频率，减少压测期间自身 I/O 干扰 |
| `no_test_connection=False` | 保留预检；若发现预检污染成功率首个数据点，Phase 2 再改 |
| 指纹归一化 | `20` 与 `20.0` 必须同指纹，否则 open_loop 任务会被误判不可比 |
| `_dispatch` 容错 | worker 未就绪时只记 warning，不让创建接口 500 |

## Phase 2 待做

1. `EvalScopeEngine.run()` 真正调用 `evalscope.perf.run_perf_benchmark()`
2. 进度回写（Redis `perf:progress:{id}`）+ 中止监听（`perf:abort:{id}`）
3. `ResultParser`：EvalScope 返回结构 → `result_json` 契约
4. `perf-worker` 镜像（`pip install evalscope`）+ compose 服务 + `perf_outputs` 卷
5. HTML 报告下载端点
