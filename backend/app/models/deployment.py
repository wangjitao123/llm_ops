from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Text, SmallInteger, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Deployment(Base):
    __tablename__ = "deployment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    deploy_type: Mapped[str] = mapped_column(String(16), nullable=False, default="managed")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="deploying")
    base_model_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=True)
    hf_model_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # 量化任务产出的模型在共享卷中的路径（由量化任务带入，容器内挂载后使用）
    model_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # 平台管理的容器信息（deploy_type=managed 时有效）
    container_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    host_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 自动注册到模型管理后，对应 model 表的记录 id
    registered_model_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("model.id"), nullable=True)
    engine: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    gpu_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Integer), nullable=True)
    gpu_count: Mapped[int] = mapped_column(SmallInteger, default=1)
    gpu_memory_gb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=32)
    max_input_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, default=0.70)
    top_p: Mapped[Optional[float]] = mapped_column(Float, default=0.90)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    frequency_penalty: Mapped[Optional[float]] = mapped_column(Float, default=0.00)
    tools_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    web_search_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    web_search_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    env_vars: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    auto_register: Mapped[bool] = mapped_column(Boolean, default=True)
    health_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)