from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, DateTime, SmallInteger, Date, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ApiRequestLog(Base):
    __tablename__ = "api_request_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    app_key_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    model_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    route_rule_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    request_path: Mapped[str] = mapped_column(String(200), nullable=False)
    request_method: Mapped[str] = mapped_column(String(10), default="POST")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    client_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TokenStatsHourly(Base):
    __tablename__ = "token_stats_hourly"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stats_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    stats_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dimension_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dimension_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cost: Mapped[float] = mapped_column(DECIMAL(18, 6), default=0)
    avg_response_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TokenStatsDaily(Base):
    __tablename__ = "token_stats_daily"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stats_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    dimension_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dimension_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cost: Mapped[float] = mapped_column(DECIMAL(18, 6), default=0)
    avg_response_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))