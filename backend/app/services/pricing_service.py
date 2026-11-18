"""模型计费单价服务。

单价只影响**后续统计**的计费：账单在小时聚合时按当时的单价算出并落库
（见 app/tasks/stats_aggregator.py），所以改价不会追溯改写历史账单 ——
这正是财务上想要的行为。
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.pricing_repo import PricingRepo
from app.schemas.pricing import PricingResponse, PricingUpsert


class PricingService:
    def __init__(self, db: AsyncSession):
        self.repo = PricingRepo(db)

    @staticmethod
    def _to_response(row) -> dict:
        model = getattr(row, "model", None)
        return PricingResponse(
            model_id=row.model_id,
            model_name=getattr(model, "name", None),
            input_price_per_1k=float(row.input_price_per_1k or 0),
            output_price_per_1k=float(row.output_price_per_1k or 0),
            currency=row.currency or "CNY",
            remark=row.remark,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        ).model_dump()

    async def list_all(self) -> dict:
        rows = await self.repo.get_all()
        unpriced = await self.repo.get_unpriced_model_ids()
        return {
            "items": [self._to_response(r) for r in rows],
            "unpriced_model_ids": unpriced,
        }

    async def get(self, model_id: int) -> Optional[dict]:
        row = await self.repo.get_by_model(model_id)
        return self._to_response(row) if row else None

    async def upsert(self, model_id: int, data: PricingUpsert, user: str) -> dict:
        payload = data.model_dump()
        payload["updated_by"] = user
        row = await self.repo.get_by_model(model_id)
        if row is None:
            payload["created_by"] = user
        row = await self.repo.upsert(model_id, payload)
        return self._to_response(row)

    async def delete(self, model_id: int) -> bool:
        return await self.repo.delete_by_model(model_id)