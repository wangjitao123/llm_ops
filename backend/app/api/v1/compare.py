from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.repositories.system_repo import SystemRepo
from app.schemas.common import ApiResponse

router = APIRouter()


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_eval(
    name: str,
    model_ids: list[int],
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = SystemRepo(db)
    result = await repo.create_model_eval({
        "name": name,
        "model_ids": model_ids,
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
    from sqlalchemy import select
    from app.models.system import ModelEval
    result = await db.execute(select(ModelEval).where(ModelEval.deleted_at.is_(None)).order_by(ModelEval.created_at.desc()))
    evals = result.scalars().all()
    return ApiResponse(data=[
        {"id": e.id, "name": e.name, "model_ids": e.model_ids, "status": e.status, "recommendation": e.recommendation, "created_at": e.created_at.isoformat()}
        for e in evals
    ])


@router.get("/{eval_id}", response_model=ApiResponse)
async def get_eval(
    eval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = SystemRepo(db)
    from sqlalchemy import select
    from app.models.system import ModelEval
    result = await db.execute(select(ModelEval).where(ModelEval.id == eval_id, ModelEval.deleted_at.is_(None)))
    eval_item = result.scalar_one_or_none()
    if not eval_item:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return ApiResponse(data={
        "id": eval_item.id,
        "name": eval_item.name,
        "model_ids": eval_item.model_ids,
        "dimension_weights": eval_item.dimension_weights,
        "status": eval_item.status,
        "result": eval_item.result,
        "recommendation": eval_item.recommendation,
        "created_at": eval_item.created_at.isoformat(),
    })