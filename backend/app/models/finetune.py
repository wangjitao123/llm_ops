from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Text, DateTime, JSON, ForeignKey, SmallInteger, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Dataset(Base):
    __tablename__ = "dataset"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    annotation_status: Mapped[str] = mapped_column(String(20), default="pending")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FinetuneTask(Base):
    __tablename__ = "finetune_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_model_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=False)
    dataset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dataset.id"), nullable=False)
    val_dataset_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("dataset.id"), nullable=True)
    hyper_params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[int] = mapped_column(SmallInteger, default=0)
    loss_value: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 6), nullable=True)
    output_model_version_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("model_version.id"), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FinetuneEval(Base):
    __tablename__ = "finetune_eval"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("finetune_task.id"), nullable=False)
    accuracy_before: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 2), nullable=True)
    accuracy_after: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 2), nullable=True)
    bleu_before: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 4), nullable=True)
    bleu_after: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 4), nullable=True)
    rouge_l_before: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 4), nullable=True)
    rouge_l_after: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 4), nullable=True)
    latency_before_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_after_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eval_report: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DatasetVersion(Base):
    """数据集版本表 - 记录数据集的历史版本（含回退所需文件快照信息）。"""

    __tablename__ = "dataset_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dataset.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    change_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))