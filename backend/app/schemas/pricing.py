"""模型计费单价 schema。"""
from typing import Optional
from pydantic import BaseModel, Field


class PricingUpsert(BaseModel):
    """新增/更新单价。单价为「元 / 千 token」，0 表示不计费。"""

    input_price_per_1k: float = Field(0, ge=0, description="元 / 千输入 token")
    output_price_per_1k: float = Field(0, ge=0, description="元 / 千输出 token")
    currency: str = Field(default="CNY", max_length=8)
    remark: Optional[str] = Field(default=None, max_length=200)


class PricingResponse(BaseModel):
    model_id: int
    model_name: Optional[str] = None
    input_price_per_1k: float = 0
    output_price_per_1k: float = 0
    currency: str = "CNY"
    remark: Optional[str] = None
    updated_at: Optional[str] = None


class PricingListResponse(BaseModel):
    items: list[PricingResponse]
    # 有模型但没有价格记录：前端用于提示"这些模型按 0 计费"
    unpriced_model_ids: list[int] = []