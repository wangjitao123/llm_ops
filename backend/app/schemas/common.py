from datetime import datetime
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = 1
    size: int = 20


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None


class AuditMixin(BaseModel):
    created_by: str | None = None
    created_at: datetime | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None