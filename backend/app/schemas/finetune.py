from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class FinetuneTaskCreate(BaseModel):
    name: str = Field(..., max_length=200)
    base_model_id: int
    dataset_id: int
    val_dataset_id: Optional[int] = None
    hyper_params: dict = Field(default_factory=lambda: {
        "learning_rate": 0.0001,
        "epochs": 3,
        "batch_size": 8,
        "lora_rank": 8,
        "lora_alpha": 16,
    })


class FinetuneTaskResponse(BaseModel):
    id: int
    name: str
    base_model_id: int
    dataset_id: int
    hyper_params: dict
    status: str
    progress: int
    loss_value: Optional[float] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DatasetCreate(BaseModel):
    name: str = Field(..., max_length=200)
    format: str = Field(..., pattern="^(jsonl|csv|json|parquet)$")
    description: Optional[str] = None


class DatasetResponse(BaseModel):
    id: int
    name: str
    format: str
    sample_count: int
    file_size: int
    version: str
    annotation_status: str
    description: Optional[str] = None
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FinetuneEvalResponse(BaseModel):
    id: int
    task_id: int
    accuracy_before: Optional[float] = None
    accuracy_after: Optional[float] = None
    eval_report: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}