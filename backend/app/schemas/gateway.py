from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RouteRuleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    path_pattern: str = Field(..., max_length=200)
    match_type: str = Field(default="exact", pattern="^(exact|prefix|regex)$")
    strategy: str = Field(default="weighted", pattern="^(weighted|active_standby|single)$")
    priority: int = 0
    model_targets: list[dict] = Field(default_factory=list)  # [{"model_id": 1, "weight": 60}]


class RouteRuleUpdate(BaseModel):
    name: Optional[str] = None
    path_pattern: Optional[str] = None
    strategy: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    model_targets: Optional[list[dict]] = None


class RouteRuleResponse(BaseModel):
    id: int
    name: str
    path_pattern: str
    match_type: str
    strategy: str
    status: str
    priority: int
    model_targets: list[dict] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RequestLogQuery(BaseModel):
    app_key_id: Optional[int] = None
    model_id: Optional[int] = None
    status_code: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    page: int = 1
    size: int = 20


class RequestLogResponse(BaseModel):
    id: int
    request_id: str
    app_key_id: Optional[int] = None
    model_id: Optional[int] = None
    request_path: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    response_time_ms: int
    status_code: int
    created_at: datetime

    model_config = {"from_attributes": True}