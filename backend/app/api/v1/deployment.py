from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.deployment import DeploymentCreate, DeploymentUpdate
from app.services.deployment_service import DeploymentService

router = APIRouter()


# ============================================================
# 注意：静态路径必须在 /{deploy_id} 之前声明，
# 否则 "quantized-models" 会被当成 deploy_id 做 int 解析而 422。
# ============================================================

@router.get("/quantized-models", response_model=ApiResponse)
async def list_quantized_models(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取已量化的模型列表（供新建部署选择）。"""
    service = DeploymentService(db)
    models = await service.get_quantized_models()
    return ApiResponse(data=[m.model_dump() for m in models])


@router.get("/gpu-topology", response_model=ApiResponse)
async def gpu_topology(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取 GPU 资源拓扑（含采集来源与不可用原因）。"""
    service = DeploymentService(db)
    return ApiResponse(data=await service.get_gpu_topology())


@router.get("", response_model=ApiResponse)
async def list_deployments(
    status: str = None,
    deploy_type: str = None,
    search: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DeploymentService(db)
    deploys = await service.list_deployments(status, deploy_type, search)
    return ApiResponse(data=deploys)


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    data: DeploymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DeploymentService(db)
    result = await service.create_deployment(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


@router.get("/{deploy_id}", response_model=ApiResponse)
async def get_deployment(
    deploy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DeploymentService(db)
    deploy = await service.get_deployment(deploy_id)
    if not deploy:
        raise HTTPException(status_code=404, detail="部署不存在")
    return ApiResponse(data=deploy)


@router.put("/{deploy_id}", response_model=ApiResponse)
async def update_deployment(
    deploy_id: int,
    data: DeploymentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DeploymentService(db)
    if not await service.get_deployment(deploy_id):
        raise HTTPException(status_code=404, detail="部署不存在")
    result = await service.update_deployment(deploy_id, data)
    return ApiResponse(data=result)


@router.delete("/{deploy_id}", response_model=ApiResponse)
async def delete_deployment(
    deploy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DeploymentService(db)
    if not await service.delete_deployment(deploy_id):
        raise HTTPException(status_code=404, detail="部署不存在")
    return ApiResponse(message="部署已删除")


@router.post("/{deploy_id}/start", response_model=ApiResponse)
async def start_deployment(
    deploy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """启动部署（仅平台管理类型）。"""
    service = DeploymentService(db)
    if not await service.get_deployment(deploy_id):
        raise HTTPException(status_code=404, detail="部署不存在")
    try:
        result = await service.start_deployment(deploy_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ApiResponse(data=result)


@router.post("/{deploy_id}/stop", response_model=ApiResponse)
async def stop_deployment(
    deploy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """停止部署（仅平台管理类型）。"""
    service = DeploymentService(db)
    if not await service.get_deployment(deploy_id):
        raise HTTPException(status_code=404, detail="部署不存在")
    try:
        result = await service.stop_deployment(deploy_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ApiResponse(data=result)


@router.post("/{deploy_id}/restart", response_model=ApiResponse)
async def restart_deployment(
    deploy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """重启部署（仅平台管理类型）。"""
    service = DeploymentService(db)
    if not await service.get_deployment(deploy_id):
        raise HTTPException(status_code=404, detail="部署不存在")
    try:
        result = await service.restart_deployment(deploy_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ApiResponse(data=result)
