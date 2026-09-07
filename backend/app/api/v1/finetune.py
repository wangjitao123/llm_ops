from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.finetune_service import FinetuneService
from app.schemas.finetune import FinetuneTaskCreate, DatasetCreate
from app.schemas.common import ApiResponse

router = APIRouter()


# Finetune Tasks
@router.get("/tasks", response_model=ApiResponse)
async def list_tasks(
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = FinetuneService(db)
    tasks = await service.list_tasks(status)
    return ApiResponse(data=tasks)


@router.post("/tasks", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: FinetuneTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = FinetuneService(db)
    result = await service.create_task(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = FinetuneService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return ApiResponse(data=task)


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse)
async def cancel_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = FinetuneService(db)
    result = await service.update_task_status(task_id, "cancelled", current_user.get("sub", "system"))
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return ApiResponse(data=result)


# Datasets
@router.get("/datasets", response_model=ApiResponse)
async def list_datasets(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = FinetuneService(db)
    datasets = await service.list_datasets()
    return ApiResponse(data=datasets)


@router.post("/datasets", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    data: DatasetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = FinetuneService(db)
    result = await service.create_dataset(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


# Evaluations
@router.get("/tasks/{task_id}/eval", response_model=ApiResponse)
async def get_task_eval(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.repositories.finetune_repo import FinetuneRepo
    repo = FinetuneRepo(db)
    eval_result = await repo.get_eval_by_task(task_id)
    if not eval_result:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return ApiResponse(data={
        "task_id": eval_result.task_id,
        "accuracy_before": float(eval_result.accuracy_before) if eval_result.accuracy_before else None,
        "accuracy_after": float(eval_result.accuracy_after) if eval_result.accuracy_after else None,
        "bleu_before": float(eval_result.bleu_before) if eval_result.bleu_before else None,
        "bleu_after": float(eval_result.bleu_after) if eval_result.bleu_after else None,
        "eval_report": eval_result.eval_report,
        "created_at": eval_result.created_at.isoformat(),
    })