from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.gateway_service import GatewayService
from app.schemas.gateway import RouteRuleCreate, RouteRuleUpdate
from app.schemas.common import ApiResponse

router = APIRouter()


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