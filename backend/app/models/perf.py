from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Text,
    SmallInteger,
    DateTime,
    Boolean,
    Float,
    ForeignKey,
    CheckConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PerfTask(Base):
    """压测任务。

    设计要点（见 docs/概要设计/v4-模型压测/数据库设计）：
      * 摘要列 + result_json 分存 —— 列表查询不解析 JSONB
      * params_json 存完整参数快照 —— 重跑/对比用
      * fingerprint 存参数指纹 —— 判定两个任务是否严格可比
      * model_id 外键 ON DELETE SET NULL + model_name_snapshot 冗余 —— 删模型不丢压测历史
    """

    __tablename__ = "perf_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("model.id", ondelete="SET NULL"), nullable=True
    )
    # 冗余模型名：模型被删后历史仍可读
    model_name_snapshot: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    mode: Mapped[str] = mapped_column(String(16), nullable=False)

    # ---- 压力参数 ----
    parallel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_concurrency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_limit: Mapped[Optional[int]] = mapped_column(Integer, default=600)

    # ---- SLA 参数 ----
    # EvalScope 的 SLA 模式是「在上下界之间搜索满足 SLA 的压力值」，不是按步长递增，
    # 所以平台侧只提供下界/上界，不提供 step（见 Phase 1 实施记录）。
    sla_metric: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    sla_threshold_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sla_lower_bound: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sla_upper_bound: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ---- 多轮参数 ----
    turns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ---- 输入构造 ----
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="random")
    input_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dataset_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # ---- 高级参数 ----
    stream: Mapped[bool] = mapped_column(Boolean, default=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    request_timeout: Mapped[int] = mapped_column(Integer, default=60)
    tokenizer_path: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # ---- 打法 ----
    target_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    via_gateway: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---- 参数快照与指纹 ----
    params_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # ---- 进度 ----
    progress_sent: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    current_rps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ---- 结果摘要 ----
    ttft_mean_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ttft_p99_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tpot_mean_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    output_throughput: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    request_throughput: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    success_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    success_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ---- 时间与错误 ----
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_perf_task_status",
        ),
        CheckConstraint(
            "mode IN ('closed_loop','open_loop','sla','multi_turn')",
            name="ck_perf_task_mode",
        ),
        Index("idx_perf_task_status_time", "status", "created_at"),
        Index("idx_perf_task_model", "model_id", "created_at"),
        Index("idx_perf_task_fingerprint", "fingerprint"),
        Index("idx_perf_task_created_by", "created_by"),
    )


class PerfTaskLog(Base):
    """压测运行日志（终端风格展示用）。"""

    __tablename__ = "perf_task_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("perf_task.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_perf_log_task_time", "task_id", "created_at"),
    )
