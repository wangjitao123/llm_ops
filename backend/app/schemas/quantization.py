from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class QuantizationTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    base_model_id: Optional[int] = None
    hf_model_id: str = Field(..., min_length=1, max_length=300)
    output_name: Optional[str] = Field(None, max_length=100)
    algorithm: str = Field(default="gptq", pattern="^(gptq|awq|bitsandbytes)$")
    weight_bits: int = Field(default=4, ge=2, le=8)
    activation_bits: int = Field(default=16, ge=8, le=32)
    group_size: int = Field(default=128, ge=32, le=256)
    calib_samples: int = Field(default=256, ge=64, le=1024)
    calib_source: str = Field(default="default", pattern="^(default|custom)$")
    calib_text: Optional[str] = None
    output_path: Optional[str] = None


class QuantizationTaskUpdate(BaseModel):
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    error_message: Optional[str] = None
    result_model_id: Optional[int] = None
    output_path: Optional[str] = None
    output_name: Optional[str] = None


class QuantizationTaskResponse(BaseModel):
    id: int
    name: str
    base_model_id: Optional[int] = None
    hf_model_id: str
    output_name: Optional[str] = None
    algorithm: str
    weight_bits: int
    activation_bits: int
    group_size: int
    calib_samples: int
    calib_source: str
    calib_text: Optional[str] = None
    output_path: Optional[str] = None
    status: str
    progress: int
    error_message: Optional[str] = None
    result_model_id: Optional[int] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)