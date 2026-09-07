from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.gateway_service import GatewayService
from app.services.proxy_service import ProxyService
from app.schemas.gateway import RouteRuleCreate, RouteRuleUpdate
from app.schemas.common import ApiResponse

router = APIRouter()


class VerifyKeyRequest(BaseModel):
    key: str = Field(..., description="平台 API Key（明文，sk- 开头）")


# 网关 Key 校验端点（供 Higress / 自研网关回调）
# 请求：{ "key": "sk-xxxx" }
# 200 = 有效并返回 key 信息；401 = 无效
@router.post("/verify-key", response_model=ApiResponse)
async def verify_key(
    data: VerifyKeyRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = ProxyService(db)
    key = await svc.authenticate_key(data.key)
    if not key:
        return ApiResponse(code=401, message="invalid key", data=None)
    # 返回该 Key 可访问的模型 id 列表（null/空 = 全部）
    allowed = await svc.list_key_allowed_model_ids(key.id)
    return ApiResponse(
        data={
            "key_id": key.id,
            "key_prefix": key.key_prefix,
            "name": key.name,
            "allowed_model_ids": allowed,
            "token_quota": key.token_quota,
            "token_used": key.token_used,
        }
    )


@router.get("/routes", response_model=ApiResponse)
async def list_routes(
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = GatewayService(db)
    routes = await service.list_routes(status)
    return ApiResponse(data=routes)


@router.post("/routes", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_route(
    data: RouteRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = GatewayService(db)
    result = await service.create_route(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


@router.get("/routes/{route_id}", response_model=ApiResponse)
async def get_route(
    route_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = GatewayService(db)
    route = await service.get_route(route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return ApiResponse(data=route)


@router.put("/routes/{route_id}", response_model=ApiResponse)
async def update_route(
    route_id: int,
    data: RouteRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = GatewayService(db)
    route = await service.update_route(route_id, data, current_user.get("sub", "system"))
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return ApiResponse(data=route)


@router.delete("/routes/{route_id}", response_model=ApiResponse)
async def delete_route(
    route_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = GatewayService(db)
    deleted = await service.delete_route(route_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Route not found")
    return ApiResponse(message="Route deleted")


@router.post("/routes/{route_id}/sync", response_model=ApiResponse)
async def sync_route_to_higress(
    route_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = GatewayService(db)
    success = await service.sync_to_higress(route_id)
    if not success:
        raise HTTPException(status_code=400, detail="Sync failed")
    return ApiResponse(message="Route synced to Higress")