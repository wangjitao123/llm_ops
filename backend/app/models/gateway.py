from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class RouteRule(Base):
    __tablename__ = "route_rule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    path_pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="exact")
    strategy: Mapped[str] = mapped_column(String(20), default="weighted")
    status: Mapped[str] = mapped_column(String(20), default="disabled")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    targets = relationship("RouteRuleModel", back_populates="route_rule")


class RouteRuleModel(Base):
    __tablename__ = "route_rule_model"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    route_rule_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("route_rule.id"), nullable=False)
    model_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    route_rule = relationship("RouteRule", back_populates="targets")


class RateLimitConfig(Base):
    __tablename__ = "rate_limit_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    global_qps: Mapped[int] = mapped_column(Integer, default=5000)
    default_key_qps: Mapped[int] = mapped_column(Integer, default=100)
    default_key_rpm: Mapped[int] = mapped_column(Integer, default=6000)
    default_key_rpd: Mapped[int] = mapped_column(Integer, default=100000)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))