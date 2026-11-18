from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class DeploymentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    deploy_type: str = Field(default="managed", pattern="^(managed|conda|docker|other)$")
    base_model_id: Optional[int] = None
    hf_model_id: Optional[str] = Field(None, max_length=256)
    # 量化任务产出路径（可选；不传时按 base_model_id 关联的量化任务回填）
    model_path: Optional[str] = Field(None, max_length=512)
    # 平台管理类型在容器就绪前可为空
    endpoint_url: str = Field(default="", max_length=512)
    engine: Optional[str] = Field(None, pattern="^(vllm|tgi|sglang)$")
    gpu_ids: Optional[list[int]] = None
    gpu_count: int = Field(default=1, ge=1, le=8)
    gpu_memory_gb: Optional[float] = None
    max_concurrency: int = Field(default=32, ge=1, le=1024)
    max_input_tokens: int = Field(default=4096, ge=256, le=131072)
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=0.70, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=0.90, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=64, le=131072)
    frequency_penalty: Optional[float] = Field(default=0.00, ge=-2.0, le=2.0)
    tools_json: Optional[list[dict]] = None
    web_search_enabled: bool = False
    web_search_config: Optional[dict] = None
    env_vars: Optional[dict] = None
    auto_register: bool = True
    health_check_enabled: bool = True


class DeploymentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    status: Optional[str] = Field(None, pattern="^(deploying|running|stopped|failed|deleted)$")
    engine: Optional[str] = Field(None, pattern="^(vllm|tgi|sglang)$")
    gpu_ids: Optional[list[int]] = None
    gpu_count: Optional[int] = Field(None, ge=1, le=8)
    gpu_memory_gb: Optional[float] = None
    max_concurrency: Optional[int] = Field(None, ge=1, le=1024)
    max_input_tokens: Optional[int] = Field(None, ge=256, le=131072)
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=64, le=131072)
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    tools_json: Optional[list[dict]] = None
    web_search_enabled: Optional[bool] = None
    web_search_config: Optional[dict] = None
    env_vars: Optional[dict] = None
    auto_register: Optional[bool] = None
    health_check_enabled: Optional[bool] = None
    error_message: Optional[str] = None


class DeploymentResponse(BaseModel):
    id: int
    name: str
    deploy_type: str
    status: str
    base_model_id: Optional[int] = None
    hf_model_id: Optional[str] = None
    model_path: Optional[str] = None
    endpoint_url: str
    container_name: Optional[str] = None
    host_port: Optional[int] = None
    registered_model_id: Optional[int] = None
    engine: Optional[str] = None
    gpu_ids: Optional[list[int]] = None
    gpu_count: int
    gpu_memory_gb: Optional[float] = None
    max_concurrency: int
    max_input_tokens: int
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: int
    frequency_penalty: Optional[float] = None
    tools_json: Optional[list[dict]] = None
    web_search_enabled: bool
    web_search_config: Optional[dict] = None
    env_vars: Optional[dict] = None
    auto_register: bool
    health_check_enabled: bool
    error_message: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GpuTopology(BaseModel):
    """单张 GPU 状态"""
    gpu_id: int
    memory_total_gb: float
    memory_used_gb: float
    memory_free_gb: float
    deployments: list[str] = []


class GpuTopologyPayload(BaseModel):
    """GPU 拓扑整体响应（含采集来源，便于排查"为什么是空的"）"""
    available: bool = False
    source: Optional[str] = None      # nvml / nvidia-smi / cache / none
    error: Optional[str] = None
    updated_at: Optional[str] = None
    gpus: list[GpuTopology] = []


class QuantizedModelItem(BaseModel):
    """量化完成的模型（供新建部署选择）"""
    task_id: int
    task_name: str
    hf_model_id: str
    algorithm: str
    weight_bits: int
    output_path: str
    model_size_gb: Optional[float] = None