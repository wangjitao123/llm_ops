import logging
from typing import Optional
from pydantic import BaseModel, field_validator
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.system import ModelEval
from app.repositories.system_repo import SystemRepo
from app.schemas.common import ApiResponse
from app.services.eval_runner import EvalRunner

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateEvalRequest(BaseModel):
    name: str
    model_ids: list[int]
    test_prompts: Optional[list[list[dict]]] = None  # [[{"role":"user","content":"..."}], ...]

    @field_validator("model_ids", mode="before")
    @classmethod
    def coerce_model_ids(cls, v):
        if v is None:
            return v
        return [int(x) for x in v]


class UpdateResultRequest(BaseModel):
    models: list[dict]  # [{"model_id": int, "scores": {"quality": 85, "ease_of_use": 80}}, ...]


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_eval(
    body: CreateEvalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = SystemRepo(db)
    result = await repo.create_model_eval({
        "name": body.name,
        "model_ids": body.model_ids,
        "test_prompts": body.test_prompts,
        "dimension_weights": {
            "quality": 30, "latency": 15, "cost": 15,
            "context": 10, "stability": 10, "throughput": 10, "ease_of_use": 10,
        },
        "status": "pending",
        "created_by": current_user.get("sub", "system"),
        "updated_by": current_user.get("sub", "system"),
    })
    return ApiResponse(data={"id": result.id, "name": result.name, "status": result.status})


@router.get("", response_model=ApiResponse)
async def list_evals(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = SystemRepo(db)
    result = await db.execute(select(ModelEval).where(ModelEval.deleted_at.is_(None)).order_by(ModelEval.created_at.desc()))
    evals = result.scalars().all()
    return ApiResponse(data=[
        {
            "id": e.id, "name": e.name, "model_ids": e.model_ids,
            "status": e.status, "recommendation": e.recommendation,
            "created_at": e.created_at.isoformat(),
        }
        for e in evals
    ])


@router.get("/{eval_id}", response_model=ApiResponse)
async def get_eval(
    eval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = SystemRepo(db)
    result = await db.execute(select(ModelEval).where(ModelEval.id == eval_id, ModelEval.deleted_at.is_(None)))
    eval_item = result.scalar_one_or_none()
    if not eval_item:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return ApiResponse(data={
        "id": eval_item.id,
        "name": eval_item.name,
        "model_ids": eval_item.model_ids,
        "test_prompts": eval_item.test_prompts,
        "dimension_weights": eval_item.dimension_weights,
        "status": eval_item.status,
        "result": eval_item.result,
        "recommendation": eval_item.recommendation,
        "created_at": eval_item.created_at.isoformat(),
    })


@router.post("/{eval_id}/run", response_model=ApiResponse)
async def run_eval(
    eval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """执行模型对比评估：发测试 prompt → 采集指标 → 算分 → 出推荐。"""
    repo = SystemRepo(db)
    result = await db.execute(select(ModelEval).where(ModelEval.id == eval_id, ModelEval.deleted_at.is_(None)))
    eval_item = result.scalar_one_or_none()
    if not eval_item:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    if eval_item.status == "completed":
        raise HTTPException(status_code=400, detail="Evaluation already completed")
    if not eval_item.model_ids or len(eval_item.model_ids) < 1:
        raise HTTPException(status_code=400, detail="No models in this evaluation")

    # 更新状态为 running
    await repo.update_model_eval(eval_id, {"status": "running"})
    await db.commit()

    try:
        runner = EvalRunner(db)
        result_data, recommendation = await runner.run(eval_item)
        await repo.update_model_eval(eval_id, {
            "status": "completed",
            "result": result_data,
            "recommendation": recommendation,
            "updated_by": current_user.get("sub", "system"),
        })
        await db.commit()
    except Exception as e:
        logger.exception("eval run failed")
        await repo.update_model_eval(eval_id, {"status": "failed"})
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

    return ApiResponse(data={
        "id": eval_item.id,
        "status": "completed",
        "result": result_data,
        "recommendation": recommendation,
    })


@router.patch("/{eval_id}/result", response_model=ApiResponse)
async def update_eval_result(
    eval_id: int,
    body: UpdateResultRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """手动更新评估结果（补充 quality/ease_of_use 等人工分后重算总分）。"""
    repo = SystemRepo(db)
    result = await db.execute(select(ModelEval).where(ModelEval.id == eval_id, ModelEval.deleted_at.is_(None)))
    eval_item = result.scalar_one_or_none()
    if not eval_item:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    if not eval_item.result:
        raise HTTPException(status_code=400, detail="Run evaluation first")

    current_result = dict(eval_item.result)
    new_models = {m["model_id"]: m["scores"] for m in body.models}

    # 合并新分数到现有结果
    for model_entry in current_result.get("models", []):
        mid = model_entry["model_id"]
        if mid in new_models:
            model_entry["scores"].update(new_models[mid])
            # 清除 need_human 标记（如果所有人工维度都已补）
            if "scores_need_human" in model_entry:
                remaining = [d for d in model_entry.get("scores_need_human", [])
                             if model_entry["scores"].get(d, 0) == 0]
                if not remaining:
                    model_entry.pop("scores_need_human", None)
                else:
                    model_entry["scores_need_human"] = remaining

    # 重算总分（全部维度含人工分）
    weights = eval_item.dimension_weights or {}
    weight_sum = sum(v for v in weights.values() if v and v > 0)
    if weight_sum > 0:
        for me in current_result.get("models", []):
            s = 0.0
            for dim, w in weights.items():
                s += me["scores"].get(dim, 0) * w
            me["total_score"] = round(s / weight_sum, 1)
        overall = max(m["total_score"] for m in current_result.get("models", []) if not m.get("error"))
        current_result["overall_score"] = overall

    await repo.update_model_eval(eval_id, {
        "result": current_result,
        "updated_by": current_user.get("sub", "system"),
    })
    await db.commit()
    return ApiResponse(data={"id": eval_id, "result": current_result})