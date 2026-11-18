"""模型计费单价 API。

挂载：/api/v1/pricing
  GET    /                 全部单价（含"未配价模型"列表）
  GET    /{model_id}       单个模型单价
  PUT    /{model_id}       设置/更新单价
  DELETE /{model_id}       清除单价（= 该模型恢复不计费）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.pricing import PricingUpsert
from app.services.pricing_service import PricingService

router = APIRouter()


@router.get("", response_model=ApiResponse)
async def list_pricing(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = PricingService(db)
    return ApiResponse(data=await service.list_all())


@router.get("/{model_id}", response_model=ApiResponse)
async def get_pricing(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = PricingService(db)
    data = await service.get(model_id)
    if data is None:
        # 未配置不是错误：调用方据 unpriced 语义自行处理
        return ApiResponse(data=None, message="该模型未配置计费单价（按 0 计费）")
    return ApiResponse(data=data)


@router.put("/{model_id}", response_model=ApiResponse)
async def upsert_pricing(
    model_id: int,
    data: PricingUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = PricingService(db)
    if not await service.repo.model_exists(model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    result = await service.upsert(model_id, data, current_user.get("sub", "system"))
    await db.commit()
    return ApiResponse(data=result, message="计费单价已保存")


@router.delete("/{model_id}", response_model=ApiResponse)
async def delete_pricing(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = PricingService(db)
    deleted = await service.delete(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pricing not found")
    await db.commit()
    return ApiResponse(message="计费单价已删除（该模型恢复不计费）")