from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SystemConfigCreate(BaseModel):
    config_key: str = Field(..., max_length=100)
    config_value: str
    config_group: str = Field(default="sso", pattern="^(sso|notification|general)$")
    description: Optional[str] = None
    encrypted: bool = False


class SystemConfigResponse(BaseModel):
    id: int
    config_key: str
    config_value: str
    config_group: str
    description: Optional[str] = None
    encrypted: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertRuleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    metric_type: str = Field(..., pattern="^(daily_token|monthly_token|daily_cost|monthly_cost)$")
    threshold_value: int
    threshold_mode: str = Field(default="fixed", pattern="^(fixed|percentage)$")
    warn_at_percent: int = Field(default=80, ge=1, le=100)
    notify_channels: list[str] = Field(default_factory=lambda: ["dingtalk"])


class AlertRuleResponse(BaseModel):
    id: int
    name: str
    metric_type: str
    threshold_value: int
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    id: int
    user_id: str
    action_type: str
    action_detail: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    client_ip: Optional[str] = None
    result: str
    created_at: datetime

    model_config = {"from_attributes": True}