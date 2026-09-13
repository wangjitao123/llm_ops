from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field


class TokenStatsQuery(BaseModel):
    dimension_type: str = Field(..., pattern="^(model|application|key)$")
    dimension_id: Optional[int] = None
    start_date: date
    end_date: date
    granularity: str = Field(default="daily", pattern="^(hourly|daily)$")


class TokenStatsPoint(BaseModel):
    date: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    request_count: int
    cost: float


class TokenStatsResponse(BaseModel):
    dimension_type: str
    dimension_id: Optional[int] = None
    dimension_name: Optional[str] = None
    points: list[TokenStatsPoint]
    total_tokens: int
    total_cost: float


class CostReportQuery(BaseModel):
    start_date: date
    end_date: date
    group_by: str = Field(default="model", pattern="^(model|application|key)$")
    export: bool = False
    export_format: str = Field(default="csv", pattern="^(csv|xlsx)$")