from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.system_service import SystemService
from app.schemas.system import SystemConfigCreate, AlertRuleCreate
from app.schemas.common import ApiResponse

router = APIRouter()


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