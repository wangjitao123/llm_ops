from typing import Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from app.models.gateway import RouteRule, RouteRuleModel, RateLimitConfig


class GatewayRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_route(self, data: dict) -> RouteRule:
        route = RouteRule(**data)
        self.db.add(route)
        await self.db.flush()
        return route

    async def get_route_by_id(self, route_id: int) -> Optional[RouteRule]:
        result = await self.db.execute(
            select(RouteRule).where(RouteRule.id == route_id, RouteRule.deleted_at.is_(None))
            .options(joinedload(RouteRule.targets))
        )
        return result.scalar_one_or_none()

    async def get_all_routes(self, status: Optional[str] = None) -> list[RouteRule]:
        stmt = select(RouteRule).where(RouteRule.deleted_at.is_(None))
        if status:
            stmt = stmt.where(RouteRule.status == status)
        stmt = stmt.order_by(RouteRule.priority, RouteRule.created_at.desc())
        result = await self.db.execute(stmt.options(joinedload(RouteRule.targets)))
        return list(result.unique().scalars().all())

    async def update_route(self, route_id: int, data: dict) -> Optional[RouteRule]:
        stmt = update(RouteRule).where(RouteRule.id == route_id).values(**data).returning(RouteRule)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_route(self, route_id: int) -> None:
        await self.db.execute(
            update(RouteRule).where(RouteRule.id == route_id).values(deleted_at=func.now())
        )

    async def set_route_targets(self, route_id: int, targets: list[dict]) -> None:
        await self.db.execute(
            update(RouteRuleModel).where(RouteRuleModel.route_rule_id == route_id).values(deleted_at=func.now())
        )
        for t in targets:
            target = RouteRuleModel(
                route_rule_id=route_id,
                model_id=t["model_id"],
                weight=t.get("weight", 1),
                priority=t.get("priority", 0),
            )
            self.db.add(target)
        await self.db.flush()

    async def get_rate_limit_config(self) -> Optional[RateLimitConfig]:
        result = await self.db.execute(
            select(RateLimitConfig).where(RateLimitConfig.config_key == "default").limit(1)
        )
        return result.scalar_one_or_none()