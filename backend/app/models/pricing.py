"""模型计费单价表。

**为什么单独建表而不是给 model 表加列**

本项目没有 Alembic，启动时靠 `create_all` 建表 —— 它只创建缺失的表，
**不会给已存在的表加列**。因此计费单价必须放在新表里，否则线上库里
永远不会有这两列（代码却以为有，直接 UndefinedColumn）。

**单位约定**

单价一律是「元 / 千 token」，与 OpenAI、各云厂商报价口径一致：

    本次费用 = 输入 token / 1000 × input_price_per_1k
             + 输出 token / 1000 × output_price_per_1k

金额列用 DECIMAL(18,6)：够表达 0.000001 元级别的单价与累计账单，
避免 float 累计误差（账单场景用 float 会越算越偏）。
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, BigInteger, DateTime, DECIMAL, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ModelPricing(Base):
    __tablename__ = "model_pricing"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 一个模型一条价格记录；未配置 = 不计费（按 0 计）
    model_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("model.id"), unique=True, nullable=False
    )
    # 元 / 千输入 token
    input_price_per_1k: Mapped[float] = mapped_column(DECIMAL(18, 6), default=0)
    # 元 / 千输出 token
    output_price_per_1k: Mapped[float] = mapped_column(DECIMAL(18, 6), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    model = relationship("Model")