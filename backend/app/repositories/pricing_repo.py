"""模型计费单价仓库。"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.model import Model
from app.models.pricing import ModelPricing


class PricingRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_model(self, model_id: int) -> Optional[ModelPricing]:
        result = await self.db.execute(
            select(ModelPricing).where(ModelPricing.model_id == model_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[ModelPricing]:
        result = await self.db.execute(
            select(ModelPricing)
            .options(joinedload(ModelPricing.model))
            .order_by(ModelPricing.model_id)
        )
        return list(result.unique().scalars().all())

    async def upsert(self, model_id: int, data: dict) -> ModelPricing:
        """存在则更新、不存在则新建（不用 ON CONFLICT，跨方言可测）。"""
        row = await self.get_by_model(model_id)
        if row is None:
            row = ModelPricing(model_id=model_id, **data)
            self.db.add(row)
        else:
            for k, v in data.items():
                setattr(row, k, v)
        await self.db.flush()
        await self.db.refresh(row, ["model"])
        return row

    async def delete_by_model(self, model_id: int) -> bool:
        row = await self.get_by_model(model_id)
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def model_exists(self, model_id: int) -> bool:
        result = await self.db.execute(
            select(Model.id).where(Model.id == model_id, Model.deleted_at.is_(None))
        )
        return result.scalar_one_or_none() is not None

    async def get_unpriced_model_ids(self) -> list[int]:
        """还没有价格记录的在线/离线模型（用于提示"按 0 计费"）。"""
        priced = select(ModelPricing.model_id)
        result = await self.db.execute(
            select(Model.id)
            .where(Model.deleted_at.is_(None), Model.id.notin_(priced))
            .order_by(Model.id)
        )
        return list(result.scalars().all())