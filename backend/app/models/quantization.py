from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Text, SmallInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class QuantizationTask(Base):
    __tablename__ = "quantization_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_model_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=True)
    hf_model_id: Mapped[str] = mapped_column(String(300), nullable=False)
    output_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    algorithm: Mapped[str] = mapped_column(String(20), default="gptq")
    weight_bits: Mapped[int] = mapped_column(SmallInteger, default=4)
    activation_bits: Mapped[int] = mapped_column(SmallInteger, default=16)
    group_size: Mapped[int] = mapped_column(Integer, default=128)
    calib_samples: Mapped[int] = mapped_column(Integer, default=256)
    calib_source: Mapped[str] = mapped_column(String(20), default="default")
    calib_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_model_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)