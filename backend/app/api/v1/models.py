from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.model_service import ModelService
from app.schemas.model import ModelCreate, ModelUpdate, ModelResponse, ModelStatusUpdate
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get("", response_model=ApiResponse)
async def list_models(
    provider: str = None,
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ModelService(db)
    models = await service.list_models(provider, status)
    return ApiResponse(data=models)


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    data: ModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ModelService(db)
    result = await service.create_model(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


@router.get("/{model_id}", response_model=ApiResponse)
async def get_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ModelService(db)
    model = await service.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return ApiResponse(data=model)


@router.put("/{model_id}", response_model=ApiResponse)
async def update_model(
    model_id: int,
    data: ModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ModelService(db)
    model = await service.update_model(model_id, data, current_user.get("sub", "system"))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return ApiResponse(data=model)


@router.delete("/{model_id}", response_model=ApiResponse)
async def delete_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ModelService(db)
    deleted = await service.delete_model(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Model not found")
    return ApiResponse(message="Model deleted")


@router.put("/{model_id}/status", response_model=ApiResponse)
async def update_model_status(
    model_id: int,
    data: ModelStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ModelService(db)
    model = await service.update_status(model_id, data.status, current_user.get("sub", "system"))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return ApiResponse(data=model)


@router.get("/{model_id}/versions", response_model=ApiResponse)
async def get_model_versions(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ModelService(db)
    versions = await service.get_versions(model_id)
    return ApiResponse(data=versions)