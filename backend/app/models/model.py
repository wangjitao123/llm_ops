from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Model(Base):
    __tablename__ = "model"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    api_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    qps_limit: Mapped[int] = mapped_column(Integer, default=100)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=60000)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    health_check_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    model_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    versions = relationship("ModelVersion", back_populates="model")
    heartbeats = relationship("ModelHeartbeat", back_populates="model")


class ModelVersion(Base):
    __tablename__ = "model_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_config_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    change_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    model = relationship("Model", back_populates="versions")


class ModelHeartbeat(Base):
    __tablename__ = "model_heartbeat"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    model = relationship("Model", back_populates="heartbeats")