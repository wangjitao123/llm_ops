from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token
from app.services.system_service import SystemService
from app.schemas.system import SystemConfigCreate, AlertRuleCreate
from app.schemas.common import ApiResponse

router = APIRouter()


class DevLoginRequest(BaseModel):
    """开发模式直连登录请求体。"""
    role: str = "admin"  # admin / developer / manager / scientist


class DevLoginResponse(BaseModel):
    token: str
    user: dict


# 开发模式直连登录（未对接公司 SSO 前使用）
# ⚠️ 仅在 settings.enable_dev_login 开启时可用；对接 SSO 后必须关闭。
@router.post("/dev-login", response_model=ApiResponse)
async def dev_login(data: DevLoginRequest | None = None):
    if not settings.enable_dev_login:
        raise HTTPException(status_code=403, detail="Dev login disabled")

    role = (data.role if data else "admin")
    role_map = {
        "admin": {"id": "dev-admin", "name": "开发管理员", "role": "admin", "roles": ["admin", "developer", "manager", "scientist"]},
        "developer": {"id": "dev-developer", "name": "开发人员", "role": "developer", "roles": ["developer"]},
        "manager": {"id": "dev-manager", "name": "业务管理者", "role": "manager", "roles": ["manager"]},
        "scientist": {"id": "dev-scientist", "name": "数据科学家", "role": "scientist", "roles": ["scientist"]},
    }
    user_info = role_map.get(role, role_map["admin"])
    token = create_access_token({"sub": user_info["id"], "role": user_info["role"], "roles": user_info["roles"]})
    return ApiResponse(data=DevLoginResponse(token=token, user=user_info).model_dump())


# SSO Configuration
@router.get("/config", response_model=ApiResponse)
async def get_configs(
    group: str = "sso",
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = SystemService(db)
    configs = await service.get_configs_by_group(group)
    return ApiResponse(data=configs)


@router.post("/config", response_model=ApiResponse)
async def set_config(
    data: SystemConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = SystemService(db)
    result = await service.set_config(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


# Alert Rules
@router.get("/alerts", response_model=ApiResponse)
async def list_alert_rules(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = SystemService(db)
    rules = await service.list_alert_rules()
    return ApiResponse(data=rules)


@router.post("/alerts", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    data: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = SystemService(db)
    result = await service.create_alert_rule(data, current_user.get("sub", "system"))
    return ApiResponse(data=result)


# Audit Logs
@router.get("/audit-logs", response_model=ApiResponse)
async def list_audit_logs(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = SystemService(db)
    result = await service.get_audit_logs(page, size)
    return ApiResponse(data=result)


# DingTalk notification config
@router.get("/notification", response_model=ApiResponse)
async def get_notification_config(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = SystemService(db)
    configs = await service.get_configs_by_group("notification")
    return ApiResponse(data=configs)