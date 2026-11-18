# Phase 2 实施记录 — 压测执行引擎

> 引擎接入已完成。本文记录**执行模型**、**从源码核实的事实**，以及**仍需实测验证的假设**。

## 交付内容

| 文件 | 说明 |
|------|------|
| `backend/app/services/perf_engine.py` | 执行层（子进程 + 进度/中止监控） |
| `backend/app/services/perf_result_parser.py` | 结果解析器（pydantic / dict 两种形态） |
| `backend/app/tasks/perf_entry.py` | 子进程入口，跑 `run_perf_benchmark()` 并落结果 JSON |
| `backend/app/tasks/perf_runner.py` | 任务生命周期（completed / failed / cancelled 三态分流） |
| `backend/app/api/v1/perf.py` | 新增 `GET /tasks/{id}/report` 下载 HTML 报告 |
| `backend/app/services/perf_service.py` | 运行中任务从 Redis 合并实时进度 |
| `deploy/perf/Dockerfile` | perf-worker 镜像（装 `evalscope[perf]`） |
| `deploy/docker-compose.yml` | 新增 `perf-worker` 服务 + `perf_outputs` 卷 |
| `backend/tests/test_perf_parser.py` | 18 个解析器测试 |

## 执行模型：为什么用子进程

EvalScope 的 `run_perf_benchmark()` **没有取消接口**。如果同进程调用：

- 用户点"中止"无法真正停下，只能等它跑完 → 违反 PRD PERF-006.3（Must）
- evalscope 内部任何崩溃会带崩 Celery worker

所以改为 **子进程执行**：

```
Celery task (perf 队列)
  └─ asyncio.to_thread(engine.run)
       ├─ 写 args.json（平台参数已翻译成 EvalScope Arguments）
       ├─ Popen: python -m app.tasks.perf_entry args.json result.json
       ├─ 每 2 秒：读 progress.json → 写 Redis（sent/total/percent/current_rps）
       │           读 Redis 中止标志 → 命中则 proc.terminate()
       │           检查硬超时 → 命中则 proc.terminate()
       └─ 子进程退出 → 读 result.json → parse_results() → result_json
```

**收益**：
- 中止真生效（`terminate()`，10 秒内生效）
- 崩溃隔离
- 结果格式由我方脚本控制，**不依赖 EvalScope 内部文件布局**

## 从源码核实的事实（不是猜的）

| 事实 | 来源 |
|------|------|
| `progress.json` 结构：`{status, pipeline, total_count, processed_count, percent, updated_at}` | `evalscope/utils/tqdm_utils/progress_tracker.py:22-31` |
| 开关：`Arguments.enable_progress_tracker=True` | `perf/arguments.py:253` |
| 输出路径：`{outputs_dir}/{timestamp}/{name}`，`no_timestamp=True` 时 `{outputs_dir}/{name}` | `perf/utils/db_util.py:130-141` |
| 结果库路径：`{outputs_dir}/benchmark_data.db`，**已存在会抛 FileExistsError** | `perf/utils/db_util.py:144-151` |
| 摘要字段 alias：`avg_ttft`↔`'Avg TTFT (ms)'`、`succeed_requests`↔`'Success Requests'` | `perf/utils/perf_models.py` BenchmarkSummary |
| 百分位：`PercentileResult.rows[]`，行含 `percentile='50%'` + `ttft/latency/tpot/output_throughput` | `perf/utils/perf_models.py` PercentileRow |
| 百分位也可能以列式落盘：`{'Percentiles': [...], 'TTFT (ms)': [...]}` | `perf/sla/sla_run.py:get_metric_values` |
| HTML 报告：`gen_perf_html_report(output_dir, results, args, output_html_name='perf_report.html')` | `perf/utils/report/generate_report.py` |
| SLA 是**上下界搜索**，`sla_params=[{metric: "<= 500ms"}]` | `perf/sla/sla_run.py:parse_sla_params` |

## 关键实现决策

| 决策 | 原因 |
|------|------|
| `outputs_dir` 按任务隔离（`{PERF_OUTPUTS_DIR}/{task_id}`） | 避免 `benchmark_data.db` 的 FileExistsError |
| `no_timestamp=True` + `name=perf_task_{id}` | 让报告/进度路径可预测 |
| `shutil.rmtree(work_dir)` 在启动前 | 重跑时清理残留，避免 DB 冲突 |
| 进度只写 Redis 不写 DB | 压测期间每 2 秒写 DB 纯属浪费，且与结果写入竞争 |
| `current_rps` 由两次采样差值自算 | `progress.json` 只有 count，没有速率 |
| 结果解析兼容 pydantic 与 dict | `run_perf_benchmark` 在不同路径返回不同形态 |
| 错误分布从 SQLite 读，**列名用 PRAGMA 自省** | 上游列名常量可能变；任何异常返回空 dict |

## ⚠️ 仍需实测验证的假设

以下是**我无法在本地验证**的点，首次真实运行时会暴露：

| # | 假设 | 若错的表现 | 修正方向 |
|---|------|-----------|----------|
| 1 | `Arguments(**kwargs)` 接受我传的全部字段（含 `no_timestamp`/`enable_progress_tracker`/`outputs_dir`） | 子进程启动即报 `TypeError`/`ValidationError`，`result.json` 里 `ok=false` | 看错误信息删掉/改名不支持的字段 |
| 2 | `python -m app.tasks.perf_entry` 在镜像内能导入 evalscope | `导入 evalscope 失败` | 检查 `evalscope[perf]` 是否真的装了 perf 子依赖 |
| 3 | `progress.json` 落在 `{work_dir}/progress.json`（而非 workers 子目录） | 进度一直不动（卡 0） | 改为递归找 `progress.json` |
| 4 | `run_perf_benchmark` 返回 `{key: {metrics, percentiles, ...}}` 且 metrics 是 pydantic 或 alias-dict | 指标全空 | 解析器已兼容两种，若第三种形态需再加 |
| 5 | `sla_params=[{"p99_ttft": "<= 500ms"}]` 被接受 | SLA 模式报 `Unknown SLA metric` 或单位错误 | 调整 metric 名或去掉单位 |
| 6 | `benchmark_data.db` 里存在 `success`/`response_messages` 列 | 错误分析为空（不影响主流程） | 按 PRAGMA 输出调整列名候选 |

**建议的验证顺序**：先跑一次最小任务（`random`、并发 10、请求 100），看 `result.json` 与 `progress.json` 的真实内容，再按上表逐项校正。

## 部署新增

```yaml
# docker-compose.yml
perf-worker:          # 新服务，-Q perf，无 GPU
  volumes: [perf_outputs:/app/perf_outputs]
api-server:
  volumes: [perf_outputs:/app/perf_outputs]   # 报告下载接口要读文件
volumes:
  perf_outputs:       # 新卷
```

`perf-worker` 与 `api-server` **必须共享 `perf_outputs` 卷** —— 否则 api-server 侧的
`GET /tasks/{id}/report` 读不到 worker 生成的文件。

## 镜像体积与版本锁定

`evalscope[perf]` 会带入 `modelscope[datasets]`、`pandas`、`nltk`、`sacrebleu` 等，
镜像预计 800MB~1.2GB。

⚠️ **首次构建成功后请立即锁定版本**：本地这份源码是 `0.0.0_dev` 快照，PyPI 版本号不同，
我无法给出准确版本号。构建后执行：

```bash
docker run --rm llm-ops-perf pip show evalscope | grep Version
# 把版本号写进 deploy/.env：EVALSCOPE_VER=1.x.x
docker compose build perf-worker   # 重建锁定
```
