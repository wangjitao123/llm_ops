from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.quantization_service import QuantizationService
from app.schemas.quantization import QuantizationTaskCreate
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get("/tasks", response_model=ApiResponse)
async def list_quantization_tasks(
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = QuantizationService(db)
    tasks = await service.list_tasks(status)
    return ApiResponse(data=tasks)


@router.post("/tasks", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_quantization_task(
    data: QuantizationTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = QuantizationService(db)
    result = await service.create_task(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_quantization_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = QuantizationService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(data=task)


@router.post("/tasks/{task_id}/submit", response_model=ApiResponse)
async def submit_quantization(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """提交量化任务到 GPU worker 执行。"""
    service = QuantizationService(db)
    result = await service.submit_quantization(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在")
    if result["status"] not in ("queued", "running"):
        raise HTTPException(status_code=400, detail=f"任务状态 {result['status']} 不允许提交")
    return ApiResponse(data=result)


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse)
async def cancel_quantization_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = QuantizationService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in ("running", "queued"):
        result = await service.update_task(task_id, status="cancelled")
        return ApiResponse(data=result)
    raise HTTPException(status_code=400, detail=f"当前状态 {task['status']} 不允许取消")


@router.post("/tasks/{task_id}/retry", response_model=ApiResponse)
async def retry_quantization_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """重试失败的量化任务。"""
    service = QuantizationService(db)
    result = await service.retry_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在")
    if result["status"] != "queued":
        raise HTTPException(status_code=400, detail=f"当前状态 {result['status']} 不允许重试")
    return ApiResponse(data=result)


@router.delete("/tasks/{task_id}", response_model=ApiResponse)
async def delete_quantization_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = QuantizationService(db)
    if not await service.delete_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(message="任务已删除")