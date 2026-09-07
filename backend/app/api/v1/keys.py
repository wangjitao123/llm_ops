from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.key_service import KeyService, ApplicationService
from app.schemas.key import KeyCreate, KeyUpdate, ApplicationCreate
from app.schemas.common import ApiResponse

router = APIRouter()

# ============================================================
# Application endpoints（/api/v1/keys/applications）
# ⚠️ 必须定义在 /{key_id} 动态路由之前并先 include，
#    否则 /applications 会被当作 {key_id} 匹配而返回 422。
# ============================================================
application_router = APIRouter()


@application_router.get("", response_model=ApiResponse)
async def list_applications(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ApplicationService(db)
    apps = await service.list_all()
    return ApiResponse(data=apps)


@application_router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    data: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = ApplicationService(db)
    result = await service.create(data.name, data.description, current_user.get("sub", "system"))
    return ApiResponse(data=result)


router.include_router(application_router, prefix="/applications")


# ============================================================
# Key endpoints（/api/v1/keys）
# ============================================================
@router.get("", response_model=ApiResponse)
async def list_keys(
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = KeyService(db)
    keys = await service.list_keys(status)
    return ApiResponse(data=keys)


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    data: KeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = KeyService(db)
    result = await service.create_key(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


@router.get("/{key_id}", response_model=ApiResponse)
async def get_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = KeyService(db)
    key = await service.get_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    return ApiResponse(data=key)


@router.put("/{key_id}", response_model=ApiResponse)
async def update_key(
    key_id: int,
    data: KeyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = KeyService(db)
    key = await service.update_key(key_id, data, current_user.get("sub", "system"))
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    return ApiResponse(data=key)


@router.delete("/{key_id}", response_model=ApiResponse)
async def delete_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = KeyService(db)
    deleted = await service.delete_key(key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found")
    return ApiResponse(message="Key deleted")
