from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class KeyCreate(BaseModel):
    name: str = Field(..., max_length=100)
    application_id: Optional[int] = None
    model_ids: list[int] = Field(default_factory=list)
    qps_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    rpd_limit: Optional[int] = None
    token_quota: Optional[int] = None
    expires_at: Optional[datetime] = None


class KeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    key_full: Optional[str] = None  # Only shown once after creation
    application_id: Optional[int] = None
    application_name: Optional[str] = None
    qps_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    rpd_limit: Optional[int] = None
    token_quota: Optional[int] = None
    token_used: int
    expires_at: Optional[datetime] = None
    status: str
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KeyUpdate(BaseModel):
    name: Optional[str] = None
    model_ids: Optional[list[int]] = None
    qps_limit: Optional[int] = None
    token_quota: Optional[int] = None
    status: Optional[str] = None


class ApplicationCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}