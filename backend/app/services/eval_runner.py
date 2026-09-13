"""模型对比评估运行器（轻量版）。

对 eval 中每个模型依次发送测试 prompt，自动采集客观指标并计算各维度评分。
"""
import logging
import math
import time
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model
from app.models.system import ModelEval
from app.services.proxy_service import ProxyService

logger = logging.getLogger(__name__)

# 未传测试集时的默认 5 条客服问句
DEFAULT_PROMPTS = [
    [{"role": "user", "content": "你好，我想查询一下我的订单到了哪里"}],
    [{"role": "user", "content": "我想退货退款，怎么操作"}],
    [{"role": "user", "content": "你们的营业时间是几点到几点"}],
    [{"role": "user", "content": "我昨天买的东西今天可以送到吗"}],
    [{"role": "user", "content": "怎么联系人工客服"}],
]

# 模型表无单价字段 → 成本按总 token 数相对评分
# 质量/易用性标记 "need_human"，总分不含这两维
HUMAN_DIMS = {"quality", "ease_of_use"}


class EvalRunner:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.svc = ProxyService(db)

    async def run(self, eval_item: ModelEval) -> dict:
        """执行评测，返回 result dict（含模型详情、各维度分、综合分）。"""
        prompts = eval_item.test_prompts or DEFAULT_PROMPTS
        model_ids = eval_item.model_ids or []
        weights = eval_item.dimension_weights or {}
        models_detail: list[dict] = []
        errors: list[dict] = []

        for mid in model_ids:
            model = await self.db.get(Model, mid)
            if not model or model.status != "online":
                errors.append({"model_id": mid, "error": "model not found or offline"})
                continue
            try:
                detail = await self._evaluate_model(model, prompts)
                models_detail.append(detail)
            except Exception as e:
                logger.exception("eval model %d failed", mid)
                errors.append({"model_id": mid, "error": str(e)})
                models_detail.append({
                    "model_id": mid, "model_name": model.name,
                    "scores": {}, "total_score": 0, "error": str(e),
                    "raw": {},
                })

        # 计算各模型各维度分（0-100）
        scored = self._compute_dimension_scores(models_detail)

        # 加权综合分（只算有客观数据的维度）
        overall = self._compute_overall(scored, weights)

        # 推荐建议
        recommendation = self._generate_recommendation(scored, weights)

        return {
            "overall_score": round(overall, 1) if overall else None,
            "models": scored,
            "errors": errors if errors else None,
        }, recommendation

    async def _evaluate_model(self, model: Model, prompts: list) -> dict:
        """对单个模型发全部测试 prompt，采集原始指标。"""
        latencies: list[float] = []
        prompt_tokens_list: list[int] = []
        completion_tokens_list: list[int] = []
        finish_reasons: list[str] = []
        status_codes: list[int] = []

        for messages in prompts:
            body = {
                "model": model.name,
                "messages": messages if isinstance(messages, list) else [messages],
                "stream": False,
                "max_tokens": 512,
            }
            start = time.perf_counter()
            try:
                resp = await self.svc.forward(model, body)
                elapsed_ms = (time.perf_counter() - start) * 1000
                status_codes.append(resp.status_code)
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usage", {}) or {}
                    pt = int(usage.get("prompt_tokens", 0) or 0)
                    ct = int(usage.get("completion_tokens", 0) or 0)
                    prompt_tokens_list.append(pt)
                    completion_tokens_list.append(ct)
                    latencies.append(elapsed_ms)
                    choices = data.get("choices", []) or []
                    finish_reasons.append(choices[0].get("finish_reason", "") if choices else "")
                else:
                    latencies.append(elapsed_ms)
                    prompt_tokens_list.append(0)
                    completion_tokens_list.append(0)
                    finish_reasons.append("")
            except httpx.TimeoutException:
                latencies.append(120000)  # 120s timeout as proxy default
                prompt_tokens_list.append(0)
                completion_tokens_list.append(0)
                finish_reasons.append("")
                status_codes.append(0)
            except httpx.HTTPError as e:
                logger.warning("eval model %s HTTP error: %s", model.name, e)
                latencies.append(60000)
                prompt_tokens_list.append(0)
                completion_tokens_list.append(0)
                finish_reasons.append("")
                status_codes.append(0)

        total_prompt = sum(prompt_tokens_list)
        total_completion = sum(completion_tokens_list)
        total_time = sum(latencies) / 1000  # seconds
        return {
            "model_id": model.id,
            "model_name": model.name,
            "scores": {},
            "total_score": 0,
            "raw": {
                "latencies": latencies,
                "prompt_tokens": prompt_tokens_list,
                "completion_tokens": completion_tokens_list,
                "finish_reasons": finish_reasons,
                "status_codes": status_codes,
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_time_s": total_time,
                "tokens_per_sec": total_completion / total_time if total_time > 0 else 0,
            },
        }

    def _compute_dimension_scores(self, models_detail: list[dict]) -> list[dict]:
        """从原始指标计算各模型各维度的 0-100 分。"""
        if not models_detail:
            return models_detail

        n = len(models_detail)

        # 提取原始值（跳过带 error 的）
        raw_lat = [m["raw"]["latencies"] for m in models_detail if not m.get("error") and m["raw"].get("latencies")]
        raw_throughput = [m["raw"]["tokens_per_sec"] for m in models_detail if not m.get("error")]
        raw_cv = [self._cv(m["raw"]["latencies"]) for m in models_detail if not m.get("error") and m["raw"].get("latencies")]
        raw_truncate = [
            sum(1 for r in m["raw"]["finish_reasons"] if r == "length") / max(len(m["raw"]["finish_reasons"]), 1)
            for m in models_detail if not m.get("error")
        ]
        raw_tokens = [m["raw"]["total_prompt_tokens"] + m["raw"]["total_completion_tokens"]
                      for m in models_detail if not m.get("error")]

        # 辅助：min/max 归一化
        def norm_minmax(arr):
            mn, mx = min(arr), max(arr)
            if mx == mn:
                return [50.0] * len(arr)
            return [(x - mn) / (mx - mn) * 100 for x in arr]

        def norm_lower_better(arr):
            """越低越好，归一化后 0-100（最低的得 100）"""
            mn, mx = min(arr), max(arr)
            if mx == mn:
                return [50.0] * len(arr)
            return [(mx - x) / (mx - mn) * 100 for x in arr]

        scores_by_dim = {}

        # 延迟：平均延迟越低越好
        avg_lats = [sum(l) / len(l) for l in raw_lat] if raw_lat else []
        if avg_lats and len(avg_lats) == n:
            scores_by_dim["latency"] = {i: round(s, 1) for i, s in enumerate(norm_lower_better(avg_lats))}

        # 吞吐量：tokens/sec 越高越好
        if raw_throughput and len(raw_throughput) == n:
            scores_by_dim["throughput"] = {i: round(s, 1) for i, s in enumerate(norm_minmax(raw_throughput))}

        # 稳定性：延迟变异系数 CV 越低越好
        if raw_cv and len(raw_cv) == n:
            cv_scores = [(1 - min(cv, 1.0)) * 100 for cv in raw_cv]
            scores_by_dim["stability"] = {i: round(max(s, 0), 1) for i, s in enumerate(cv_scores)}

        # 上下文：finish_reason='length' 占比越低越好（截断少 = 上下文足）
        if raw_truncate and len(raw_truncate) == n:
            scores_by_dim["context"] = {i: round(max((1 - t) * 100, 0), 1) for i, t in enumerate(raw_truncate)}

        # 成本：总 token 越少越好（相对评分）
        if raw_tokens and len(raw_tokens) == n:
            scores_by_dim["cost"] = {i: round(s, 1) for i, s in enumerate(norm_lower_better(raw_tokens))}

        # 质量/易用性（需人工）
        for dim in HUMAN_DIMS:
            scores_by_dim[dim] = {i: 0 for i in range(n)}

        # 回填到每个模型
        for i, m in enumerate(models_detail):
            scores = {}
            for dim, score_map in scores_by_dim.items():
                scores[dim] = score_map.get(i, 0)
            m["scores"] = scores
            m["scores_need_human"] = list(HUMAN_DIMS)
            # 暂不算总分（由 _compute_overall 统一算）
        return models_detail

    def _compute_overall(self, models_detail: list[dict], weights: dict) -> Optional[float]:
        """按权重计算每个模型的加权总分（只算有客观数据的维度）。"""
        if not models_detail:
            return None
        total = 0.0
        weight_sum = 0.0
        for dim, w in (weights or {}).items():
            if dim in HUMAN_DIMS or w is None or w <= 0:
                continue
            # 取第一个模型的该维度分做校验（所有模型该维都有分或都没分）
            if all(dim in m["scores"] for m in models_detail):
                total += w
                weight_sum += w
        if weight_sum <= 0:
            return None
        # 各模型各自算总分（加权平均）
        for m in models_detail:
            s = 0.0
            for dim, w in (weights or {}).items():
                if dim in HUMAN_DIMS or w is None or w <= 0:
                    continue
                score_val = m["scores"].get(dim, 0)
                s += score_val * w
            m["total_score"] = round(s / weight_sum, 1) if weight_sum > 0 else 0
        # 返回最高分
        return max(m["total_score"] for m in models_detail)

    def _generate_recommendation(self, models_detail: list[dict], weights: dict) -> str:
        """生成推荐建议（最高分模型 + 优势维度说明）。"""
        if not models_detail:
            return "评测结果为空，请确认模型可用"
        if not any(not m.get("error") for m in models_detail):
            return "所有模型均不可用，请检查模型状态"

        # 找出最高分模型
        best = max(models_detail, key=lambda m: m.get("total_score", 0) if not m.get("error") else -1)
        if best.get("total_score", 0) <= 0:
            return "评测数据不足，无法生成推荐建议"

        # 找出该模型相对于其他模型的优势维度
        advantages = []
        for dim in (weights or {}):
            if dim in HUMAN_DIMS:
                continue
            best_score = best["scores"].get(dim, 0)
            if best_score <= 0:
                continue
            others_avg = 0
            count = 0
            for m in models_detail:
                if m["model_id"] == best["model_id"] or m.get("error"):
                    continue
                others_avg += m["scores"].get(dim, 0)
                count += 1
            if count > 0:
                others_avg /= count
                if best_score > others_avg + 5:  # 领先超过 5 分算优势
                    advantages.append(dim)

        dim_names = {"latency": "延迟", "throughput": "吞吐量", "stability": "稳定性",
                     "context": "上下文", "cost": "成本", "quality": "生成质量", "ease_of_use": "易用性"}
        adv_text = "、".join(dim_names.get(d, d) for d in advantages) if advantages else "综合表现"
        return f"推荐使用「{best['model_name']}」（综合评分 {best['total_score']}），{adv_text} 方面表现较优"

    @staticmethod
    def _cv(values: list[float]) -> float:
        """变异系数 = std / mean"""
        if not values or len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        if mean <= 0:
            return 0
        var = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(var) / mean