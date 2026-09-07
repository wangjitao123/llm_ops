from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Application(Base):
    __tablename__ = "application"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    keys = relationship("AppKey", back_populates="application")


class AppKey(Base):
    __tablename__ = "app_key"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    application_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("application.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    qps_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rpm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rpd_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_quota: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    token_used: Mapped[int] = mapped_column(BigInteger, default=0)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    application = relationship("Application", back_populates="keys")
    model_permissions = relationship("AppKeyModel", back_populates="app_key")


class AppKeyModel(Base):
    __tablename__ = "app_key_model"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_key_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_key.id"), nullable=False)
    model_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    app_key = relationship("AppKey", back_populates="model_permissions")