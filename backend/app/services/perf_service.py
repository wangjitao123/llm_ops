"""模型压测任务服务。

职责边界（Phase 1）：
  * 任务 CRUD、参数校验（含**仅自建模型可压测**的硬限制）
  * 参数快照 + 参数指纹
  * 目标 URL 解析（直连模型 / 经网关）
  * 任务派发到 perf 队列
  * 结果读取与历史对比

真正的压测执行在 Phase 2（app/services/perf_engine.py + app/tasks/perf_runner.py）。
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.model_repo import ModelRepo
from app.repositories.perf_repo import PerfTaskRepo
from app.schemas.perf import (
    PerfCompareItem,
    PerfCompareResponse,
    PerfTaskCreate,
    PerfTaskDetailResponse,
    PerfTaskResponse,
)
from app.services.perf_fingerprint import compute_fingerprint, diff_fingerprint_fields

logger = logging.getLogger(__name__)

CHAT_COMPLETIONS_PATH = "/chat/completions"


class PerfValidationError(ValueError):
    """参数校验失败（对用户可见的 400 错误）。"""


class PerfService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PerfTaskRepo(db)
        self.model_repo = ModelRepo(db)

    # ==================================================
    # 创建
    # ==================================================
    async def create_task(self, data: PerfTaskCreate, user: str) -> dict:
        model = await self.model_repo.get_by_id(data.model_id)
        if model is None:
            raise PerfValidationError(f"模型不存在: id={data.model_id}")

        self._assert_model_testable(model)
        self._assert_limits(data)
        self._assert_tokenizer_available(data, model)
        self._assert_gateway_key_available(data)

        target_url = self._resolve_target_url(model, data.via_gateway)

        payload = data.model_dump()
        payload.update(
            {
                "status": "pending",
                "model_name_snapshot": model.name,
                "target_url": target_url,
                "created_by": user,
                "progress_sent": 0,
                "progress_total": self._expected_total(data),
                # 完整参数快照：重跑与对比的事实源
                "params_json": data.model_dump(mode="json"),
            }
        )
        # 指纹基于「落地后的字段」，确保与后续对比逻辑一致
        payload["fingerprint"] = compute_fingerprint(payload)

        task = await self.repo.create(payload)
        await self.repo.add_log(task.id, "info", f"任务已创建，目标 {target_url}")
        await self.db.commit()

        # 派发到 perf 队列（独立 worker 消费）
        self._dispatch(task.id)

        return self._to_response(task)

    def _assert_model_testable(self, model) -> None:
        """校验模型允许压测。

        **默认不限制**（白名单留空 = 全部允许），因为平台上的模型基本都是自建部署。
        仅当显式配置了 `PERF_TESTABLE_PROVIDER_PREFIX` 时，才按 provider 前缀过滤
        —— 那是给"想禁止误压第三方付费 API"的场景预留的开关。
        """
        if self.is_testable_provider(model.provider):
            return
        allowed = "、".join(self._testable_prefixes())
        raise PerfValidationError(
            f"模型的 provider={model.provider or '空'} 不在压测白名单（{allowed}）内。"
            f"如需允许，请调整 PERF_TESTABLE_PROVIDER_PREFIX，或清空该配置以取消限制。"
        )

    @staticmethod
    def _assert_tokenizer_available(data: PerfTaskCreate, model) -> None:
        """random 数据集必须有 tokenizer，否则 EvalScope 直接 AssertionError。

        提前在创建阶段拦住，好过让用户等 7 秒后看到一条子进程报错。
        可用来源：任务里填的 tokenizer_path，或模型的 model_config.hf_model_id。
        """
        if data.dataset_type != "random":
            return
        if (data.tokenizer_path or "").strip():
            return
        cfg = model.model_config if isinstance(model.model_config, dict) else {}
        if ((cfg or {}).get("hf_model_id") or "").strip():
            return
        raise PerfValidationError(
            "random 数据集需要 tokenizer 才能按 token 精确控制输入/输出长度，"
            "但该模型未配置 hf_model_id，且未填写 tokenizer_path。请二选一："
            "① 新建压测时填 tokenizer_path（如 Qwen/Qwen2.5-7B-Instruct，或容器内本地目录）；"
            "② 在模型管理里给该模型补 model_config.hf_model_id。"
            "（也可以改用 speed_benchmark / openqa 等不需要 tokenizer 的数据集）"
        )

    @staticmethod
    def _assert_gateway_key_available(data: PerfTaskCreate) -> None:
        """经网关压测必须配置平台 API Key，否则网关直接 401。

        EvalScope 的连接预检对 401 属于 non-retryable，会立刻抛
        `TimeoutError: Test connection failed` —— 报错信息完全看不出是鉴权问题，
        因此在这里提前拦住。
        """
        if not data.via_gateway:
            return
        if (settings.perf_gateway_api_key or "").strip():
            return
        raise PerfValidationError(
            "经网关压测需要在服务端配置平台 API Key（PERF_GATEWAY_API_KEY），"
            "否则网关会返回 401。请在 API Key 管理页面创建一个 AppKey，"
            "写入 deploy/.env 的 PERF_GATEWAY_API_KEY 后重启 perf-worker；"
            "或者把「压测打法」改成「直连模型」。"
        )

    def _assert_limits(self, data: PerfTaskCreate) -> None:
        """数值上限校验（上限来自 settings，可运行时调整）。"""
        if data.parallel and data.parallel > settings.perf_max_parallel:
            raise PerfValidationError(
                f"并发数 {data.parallel} 超过平台上限 {settings.perf_max_parallel}"
            )
        if data.max_concurrency and data.max_concurrency > settings.perf_max_parallel:
            raise PerfValidationError(
                f"并发上限 {data.max_concurrency} 超过平台上限 {settings.perf_max_parallel}"
            )
        if data.sla_upper_bound and data.sla_upper_bound > settings.perf_max_parallel:
            raise PerfValidationError(
                f"SLA 搜索上界 {data.sla_upper_bound} 超过平台上限 {settings.perf_max_parallel}"
            )
        if data.number and data.number > settings.perf_max_number:
            raise PerfValidationError(
                f"请求数 {data.number} 超过平台上限 {settings.perf_max_number}"
            )

    @staticmethod
    def _resolve_target_url(model, via_gateway: bool) -> str:
        """解析压测目标 URL（完整到 /chat/completions）。"""
        if via_gateway:
            base = settings.perf_gateway_base_url.rstrip("/")
        else:
            base = (model.api_base_url or "").rstrip("/")
        if not base:
            raise PerfValidationError(f"模型「{model.name}」未配置 api_base_url，无法压测")
        if base.endswith(CHAT_COMPLETIONS_PATH):
            return base
        return f"{base}{CHAT_COMPLETIONS_PATH}"

    @staticmethod
    def _expected_total(data: PerfTaskCreate) -> int:
        """预期总请求数（用于进度条分母）。"""
        if data.mode == "multi_turn" and data.turns and data.number:
            return int(data.turns) * int(data.number)
        return int(data.number or 0)

    @staticmethod
    def _dispatch(task_id: int) -> None:
        """投递到 perf 队列。worker 未就绪时记日志但不阻塞用户。"""
        try:
            from app.tasks.perf_runner import run_perf_task

            run_perf_task.apply_async(args=[task_id], queue="perf")
        except Exception:  # noqa: BLE001 - 派发失败不应让创建接口 500
            logger.warning("压测任务 %s 派发失败（worker 可能未就绪）", task_id, exc_info=True)

    # ==================================================
    # 查询
    # ==================================================
    def _to_response(self, task) -> dict:
        return PerfTaskResponse.model_validate(task).model_dump()

    def _to_detail(self, task) -> dict:
        return PerfTaskDetailResponse.model_validate(task).model_dump()

    async def get_task(self, task_id: int) -> Optional[dict]:
        task = await self.repo.get_by_id(task_id)
        if task is None:
            return None
        data = self._to_detail(task)
        if task.status == "running":
            await self._merge_live_progress(task_id, data)
        return data

    async def _merge_live_progress(self, task_id: int, data: dict) -> None:
        """运行中任务：从 Redis 合并实时进度（worker 侧每 2 秒回写一次）。

        进度不入库的原因：压测期间每 2 秒写一次 DB 纯属浪费，
        且会与任务结果写入竞争；Redis 是天然适合的载体。
        """
        import json

        from app.core.redis import redis_client

        try:
            raw = await redis_client.get(f"{settings.perf_redis_prefix}:progress:{task_id}")
        except Exception:  # noqa: BLE001 - Redis 不可用时退回 DB 里的旧值
            return
        if not raw:
            return
        try:
            snap = json.loads(raw)
        except (TypeError, ValueError):
            return

        if snap.get("sent") is not None:
            data["progress_sent"] = int(snap["sent"])
        if snap.get("total"):
            data["progress_total"] = int(snap["total"])
        if snap.get("current_rps") is not None:
            data["current_rps"] = float(snap["current_rps"])

    async def list_tasks(
        self,
        status: Optional[str] = None,
        model_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        tasks = await self.repo.get_all(status=status, model_id=model_id, search=search)
        return [self._to_response(t) for t in tasks]

    async def get_stats(self) -> dict:
        return await self.repo.stats()

    async def get_logs(self, task_id: int) -> list[dict]:
        logs = await self.repo.get_logs(task_id)
        return [
            {"level": lg.level, "message": lg.message, "created_at": lg.created_at.isoformat()}
            for lg in logs
        ]

    async def get_engine_log(self, task_id: int, lines: int = 200) -> dict:
        """读取压测子进程的实时输出（engine.log 尾部）。

        压测"看起来卡住"时，这里能看到 EvalScope 实际在干什么：
        下载 tokenizer、压测中、还是抛异常。
        """
        import os

        from app.services.perf_engine import task_work_dir

        path = os.path.join(task_work_dir(task_id), "engine.log")
        if not os.path.exists(path):
            return {
                "exists": False,
                "content": "",
                "hint": "子进程还没产生输出（可能仍在导入 evalscope / 下载 tokenizer），稍后再看",
            }
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            return {"exists": False, "content": "", "hint": f"读取失败: {e}"}

        tail = "\n".join(content.splitlines()[-lines:])
        return {"exists": True, "content": tail, "lines": lines, "size": len(content)}

    async def get_report_path(self, task_id: int) -> Optional[str]:
        """返回 EvalScope 原生 HTML 报告的磁盘路径；不存在返回 None。"""
        import os

        task = await self.repo.get_by_id(task_id)
        if task is None:
            return None

        candidates = []
        if task.result_json:
            candidates.append((task.result_json or {}).get("report_path"))

        from app.services.perf_engine import report_path_for

        candidates.append(report_path_for(task_id))

        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    # ==================================================
    # 操作
    # ==================================================
    async def cancel_task(self, task_id: int) -> Optional[dict]:
        """中止任务。

        * pending：直接改 cancelled（worker 不会再执行）
        * running：置中止标志，worker 轮询到后优雅停止并落已采集数据
        """
        task = await self.repo.get_by_id(task_id)
        if task is None:
            return None
        if task.status not in ("pending", "running"):
            raise PerfValidationError(f"当前状态 {task.status} 不允许中止")

        from app.core.redis import redis_client

        try:
            await redis_client.set(f"{settings.perf_redis_prefix}:abort:{task_id}", "1", ex=3600)
        except Exception:  # noqa: BLE001 - Redis 不可用时仍允许强改状态
            logger.warning("设置中止标志失败 task=%s", task_id, exc_info=True)

        if task.status == "pending":
            updated = await self.repo.update(
                task_id,
                {
                    "status": "cancelled",
                    "finished_at": datetime.now(timezone.utc),
                    "error_message": "已被用户中止（未开始执行）",
                },
            )
            await self.repo.add_log(task_id, "warn", "任务在排队阶段被用户中止")
            await self.db.commit()
            return self._to_response(updated)

        await self.repo.add_log(task_id, "warn", "已发送中止信号，等待 worker 停止")
        await self.db.commit()
        return self._to_response(task)

    async def rerun_task(self, task_id: int, new_name: Optional[str], user: str) -> dict:
        """用相同参数重跑：基于参数快照创建新任务。"""
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise PerfValidationError(f"任务不存在: id={task_id}")
        if not task.params_json:
            raise PerfValidationError("该任务缺少参数快照，无法重跑")

        if task.model_id is None:
            raise PerfValidationError("原任务的模型已被删除，无法重跑")

        snapshot = dict(task.params_json)
        snapshot["name"] = new_name or f"{task.name} (重跑)"
        snapshot["model_id"] = task.model_id

        data = PerfTaskCreate(**snapshot)
        return await self.create_task(data, user)

    async def delete_task(self, task_id: int) -> bool:
        task = await self.repo.get_by_id(task_id)
        if task is None:
            return False
        if task.status == "running":
            raise PerfValidationError("任务正在运行，请先中止再删除")
        ok = await self.repo.delete(task_id)
        await self.db.commit()
        return ok

    # ==================================================
    # 可压测模型列表（前端下拉用）
    # ==================================================
    @staticmethod
    def _testable_prefixes() -> list[str]:
        """解析 provider 白名单（逗号分隔，小写）。**返回空列表表示不限制**。"""
        raw = settings.perf_testable_provider_prefix or ""
        return [p.strip().lower() for p in raw.split(",") if p.strip()]

    @classmethod
    def is_testable_provider(cls, provider: Optional[str]) -> bool:
        """该 provider 是否允许压测。

        白名单留空 → 全部允许（平台上的模型都是自建时的默认行为）。
        白名单非空 → 只允许前缀命中的 provider。
        """
        prefixes = cls._testable_prefixes()
        if not prefixes:
            return True
        prov = (provider or "").strip().lower()
        if not prov:
            return False
        return any(prov.startswith(p) for p in prefixes)

    async def list_testable_models(self) -> list[dict]:
        """返回可压测的模型（默认全部，除非配置了 provider 白名单）。

        不过滤 status：模型 status 要健康检查跑过才变 online，新建/未巡检的会停在
        pending —— 若按 status 过滤，下拉会空，用户根本没法发起第一次压测
        （而压测本身就是验证可用性的手段）。status 随返回体带给前端做提示。
        """
        models = await self.model_repo.get_all()
        result = []
        for m in models:
            if not self.is_testable_provider(m.provider):
                continue
            result.append(
                {
                    "id": m.id,
                    "name": m.name,
                    "provider": m.provider,
                    "status": m.status,
                    "api_base_url": m.api_base_url,
                    "hf_model_id": (m.model_config or {}).get("hf_model_id")
                    if isinstance(m.model_config, dict)
                    else None,
                }
            )
        return result

    # ==================================================
    # 历史对比
    # ==================================================
    async def compare_tasks(self, task_ids: list[int]) -> PerfCompareResponse:
        if not 2 <= len(task_ids) <= 4:
            raise PerfValidationError("对比需要选择 2-4 个任务")

        tasks = []
        for tid in task_ids:
            task = await self.repo.get_by_id(tid)
            if task is None:
                raise PerfValidationError(f"任务不存在: id={tid}")
            if task.status != "completed":
                raise PerfValidationError(
                    f"任务「{task.name}」状态为 {task.status}，只有已完成的任务可对比"
                )
            tasks.append(task)

        items = [self._to_compare_item(t) for t in tasks]

        # 指纹一致性
        fingerprints = {t.fingerprint for t in tasks if t.fingerprint}
        strictly = len(fingerprints) == 1 and all(t.fingerprint for t in tasks)

        diff_fields: list[str] = []
        if not strictly:
            base = tasks[0]
            acc: list[str] = []
            for t in tasks[1:]:
                for name in diff_fingerprint_fields(base, t):
                    if name not in acc:
                        acc.append(name)
            diff_fields = acc

        deltas = self._compute_deltas(items)
        return PerfCompareResponse(
            items=items,
            strictly_comparable=strictly,
            diff_fields=diff_fields,
            deltas=deltas,
        )

    @staticmethod
    def _to_compare_item(task) -> PerfCompareItem:
        """从任务 + result_json 提取对比所需指标。"""
        result = task.result_json or {}
        percentiles = result.get("percentiles") or {}
        ttft_pct = percentiles.get("ttft") or {}

        def _num(*candidates):
            for c in candidates:
                if c is not None:
                    return c
            return None

        return PerfCompareItem(
            task_id=task.id,
            name=task.name,
            created_at=task.created_at,
            mode=task.mode,
            model_name=task.model_name_snapshot,
            parallel=task.parallel,
            rate=task.rate,
            number=task.number,
            dataset_type=task.dataset_type,
            input_length=task.input_length,
            output_length=task.output_length,
            stream=bool(task.stream),
            fingerprint=task.fingerprint,
            ttft_mean_ms=task.ttft_mean_ms,
            ttft_p50_ms=_num(ttft_pct.get("p50"), ttft_pct.get("P50")),
            ttft_p90_ms=_num(ttft_pct.get("p90"), ttft_pct.get("P90")),
            ttft_p99_ms=_num(task.ttft_p99_ms, ttft_pct.get("p99"), ttft_pct.get("P99")),
            tpot_mean_ms=task.tpot_mean_ms,
            output_throughput=task.output_throughput,
            request_throughput=task.request_throughput,
            success_rate=task.success_rate,
            duration_seconds=task.duration_seconds,
        )

    @staticmethod
    def _compute_deltas(items: list[PerfCompareItem]) -> dict[str, list[Optional[float]]]:
        """以第一个任务为基准，计算各指标相对变化百分比。

        延迟类指标（TTFT/TPOT）越低越好，吞吐类越高越好 —— 但这里只给原始变化率，
        好坏判断交给前端着色（避免把业务语义混进数据层）。
        """
        if not items:
            return {}
        base = items[0]
        metrics = (
            "ttft_mean_ms",
            "ttft_p99_ms",
            "tpot_mean_ms",
            "output_throughput",
            "request_throughput",
            "success_rate",
        )
        deltas: dict[str, list[Optional[float]]] = {}
        for metric in metrics:
            base_val = getattr(base, metric)
            row: list[Optional[float]] = []
            for it in items:
                val = getattr(it, metric)
                if base_val in (None, 0) or val is None:
                    row.append(None)
                else:
                    row.append(round((val - base_val) / base_val * 100, 2))
            deltas[metric] = row
        return deltas
