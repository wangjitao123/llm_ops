from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ModelCreate(BaseModel):
    name: str = Field(..., max_length=100)
    provider: str = Field(..., max_length=50)
    api_base_url: str = Field(..., max_length=500)
    api_key: str = Field(..., max_length=500)
    qps_limit: int = Field(default=100, ge=1)
    timeout_ms: int = Field(default=60000, ge=1000)
    weight: int = Field(default=1, ge=1)
    health_check_url: Optional[str] = None
    model_config: Optional[dict] = None
    description: Optional[str] = None


class ModelUpdate(BaseModel):
    name: Optional[str] = None
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    qps_limit: Optional[int] = None
    timeout_ms: Optional[int] = None
    weight: Optional[int] = None
    health_check_url: Optional[str] = None
    model_config: Optional[dict] = None
    description: Optional[str] = None


class ModelResponse(BaseModel):
    id: int
    name: str
    provider: str
    version: str
    api_base_url: str
    qps_limit: int
    timeout_ms: int
    weight: int
    status: str
    health_check_url: Optional[str] = None
    model_config: Optional[dict] = None
    description: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(online|offline)$")


class ModelVersionResponse(BaseModel):
    id: int
    model_id: int
    version: str
    is_current: bool
    change_log: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}