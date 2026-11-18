from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

PerfMode = Literal["closed_loop", "open_loop", "sla", "multi_turn"]
PerfStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

# 与 EvalScope 的 dataset 名称对齐
DATASET_TYPES = (
    "random",
    "openqa",
    "speed_benchmark",
    "share_gpt",
    "line_by_line",
    "longalpaca",
    "custom",
)


class PerfTaskCreate(BaseModel):
    """创建压测任务。

    只做基本形态校验（正值、枚举）；**数值上限校验放在 Service 层**，
    因为上限来自 settings，需要可运行时调整。
    """

    name: str = Field(..., min_length=1, max_length=128)
    model_id: int = Field(..., ge=1)
    mode: PerfMode

    # 压力参数
    parallel: Optional[int] = Field(None, ge=1)
    number: Optional[int] = Field(None, ge=1)
    rate: Optional[float] = Field(None, gt=0)
    max_concurrency: Optional[int] = Field(None, ge=1)
    duration_limit: int = Field(default=600, ge=10, le=7200)

    # SLA（EvalScope 为上下界搜索，不是步进）
    sla_metric: Optional[Literal["ttft", "tpot", "latency"]] = None
    sla_threshold_ms: Optional[int] = Field(None, ge=1)
    sla_lower_bound: Optional[int] = Field(None, ge=1)
    sla_upper_bound: Optional[int] = Field(None, ge=1)

    # 多轮
    turns: Optional[int] = Field(None, ge=1, le=100)

    # 输入构造
    dataset_type: str = Field(default="random")
    input_length: Optional[int] = Field(None, ge=1, le=131072)
    output_length: Optional[int] = Field(None, ge=1, le=32768)
    dataset_file: Optional[str] = Field(None, max_length=512)

    # 高级
    stream: bool = True
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    request_timeout: int = Field(default=60, ge=1, le=600)
    tokenizer_path: Optional[str] = Field(None, max_length=256)

    # 打法
    via_gateway: bool = False

    @model_validator(mode="after")
    def _check_mode_requirements(self):
        """按模式校验必填参数。"""
        if self.dataset_type not in DATASET_TYPES:
            raise ValueError(f"不支持的数据集类型: {self.dataset_type}")

        if self.mode == "closed_loop":
            if not self.parallel:
                raise ValueError("闭环并发模式必须指定 parallel（并发数）")
            if not self.number:
                raise ValueError("闭环并发模式必须指定 number（总请求数）")

        elif self.mode == "open_loop":
            if not self.rate:
                raise ValueError("开环限速模式必须指定 rate（目标 RPS）")
            if not self.number:
                raise ValueError("开环限速模式必须指定 number（总请求数）")

        elif self.mode == "sla":
            if not self.sla_metric:
                raise ValueError("SLA 模式必须指定 sla_metric")
            if not self.sla_threshold_ms:
                raise ValueError("SLA 模式必须指定 sla_threshold_ms")
            if not self.sla_lower_bound:
                raise ValueError("SLA 模式必须指定 sla_lower_bound（搜索下界）")
            if not self.sla_upper_bound:
                raise ValueError("SLA 模式必须指定 sla_upper_bound（搜索上界）")
            if self.sla_upper_bound <= self.sla_lower_bound:
                raise ValueError("sla_upper_bound 必须大于 sla_lower_bound")

        elif self.mode == "multi_turn":
            if not self.parallel:
                raise ValueError("多轮对话模式必须指定 parallel")
            if not self.turns:
                raise ValueError("多轮对话模式必须指定 turns（轮数）")
            if not self.number:
                raise ValueError("多轮对话模式必须指定 number（每轮请求数）")

        # random 数据集必须有长度，否则无法生成负载
        if self.dataset_type == "random":
            if not self.input_length:
                raise ValueError("random 数据集必须指定 input_length")
            if not self.output_length:
                raise ValueError("random 数据集必须指定 output_length")

        return self


class PerfTaskRerun(BaseModel):
    """用相同参数重跑：只允许改任务名。"""

    name: Optional[str] = Field(None, min_length=1, max_length=128)


class PerfTaskLogItem(BaseModel):
    level: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PerfTaskResponse(BaseModel):
    id: int
    name: str
    model_id: Optional[int] = None
    model_name_snapshot: Optional[str] = None
    status: str
    mode: str

    parallel: Optional[int] = None
    number: Optional[int] = None
    rate: Optional[float] = None
    max_concurrency: Optional[int] = None
    duration_limit: Optional[int] = None

    sla_metric: Optional[str] = None
    sla_threshold_ms: Optional[int] = None
    sla_lower_bound: Optional[int] = None
    sla_upper_bound: Optional[int] = None

    turns: Optional[int] = None

    dataset_type: str
    input_length: Optional[int] = None
    output_length: Optional[int] = None
    dataset_file: Optional[str] = None

    stream: bool = True
    temperature: Optional[float] = None
    request_timeout: int = 60
    tokenizer_path: Optional[str] = None

    target_url: Optional[str] = None
    via_gateway: bool = False

    fingerprint: Optional[str] = None

    progress_sent: int = 0
    progress_total: int = 0
    current_rps: Optional[float] = None

    ttft_mean_ms: Optional[float] = None
    ttft_p99_ms: Optional[float] = None
    tpot_mean_ms: Optional[float] = None
    output_throughput: Optional[float] = None
    request_throughput: Optional[float] = None
    success_rate: Optional[float] = None
    success_count: Optional[int] = None

    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PerfTaskDetailResponse(PerfTaskResponse):
    """详情：额外带全量结果与参数快照。"""

    result_json: Optional[dict] = None
    params_json: Optional[dict] = None


class PerfStats(BaseModel):
    """列表页顶部统计卡片。"""

    total: int = 0
    completed: int = 0
    running: int = 0
    latest_ttft_p99_ms: Optional[float] = None


class PerfCompareItem(BaseModel):
    """单个任务在对比视图中的指标。"""

    task_id: int
    name: str
    created_at: datetime
    mode: str
    model_name: Optional[str] = None
    parallel: Optional[int] = None
    rate: Optional[float] = None
    number: Optional[int] = None
    dataset_type: str
    input_length: Optional[int] = None
    output_length: Optional[int] = None
    stream: bool = True
    fingerprint: Optional[str] = None

    ttft_mean_ms: Optional[float] = None
    ttft_p50_ms: Optional[float] = None
    ttft_p90_ms: Optional[float] = None
    ttft_p99_ms: Optional[float] = None
    tpot_mean_ms: Optional[float] = None
    output_throughput: Optional[float] = None
    request_throughput: Optional[float] = None
    success_rate: Optional[float] = None
    duration_seconds: Optional[int] = None


class PerfCompareResponse(BaseModel):
    """历史对比结果。"""

    items: list[PerfCompareItem] = []
    # 指纹是否全部一致（True = 严格可比）
    strictly_comparable: bool = False
    # 各任务间的差异字段中文名（空 = 无差异）
    diff_fields: list[str] = []
    # 以第一个任务为基准的相对变化百分比，key=指标名，value=[基准为 None 的占位]
    deltas: dict[str, list[Optional[float]]] = {}
