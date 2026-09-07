from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.gateway_repo import GatewayRepo
from app.schemas.gateway import RouteRuleCreate, RouteRuleUpdate


class GatewayService:
    def __init__(self, db: AsyncSession):
        self.repo = GatewayRepo(db)

    async def create_route(self, data: RouteRuleCreate, user: str) -> dict:
        route_data = {
            "name": data.name,
            "path_pattern": data.path_pattern,
            "match_type": data.match_type,
            "strategy": data.strategy,
            "priority": data.priority,
            "created_by": user,
            "updated_by": user,
        }
        route = await self.repo.create_route(route_data)
        
        if data.model_targets:
            await self.repo.set_route_targets(route.id, data.model_targets)
        
        return self._to_response(route)

    async def get_route(self, route_id: int) -> Optional[dict]:
        route = await self.repo.get_route_by_id(route_id)
        if not route:
            return None
        return self._to_response(route)

    async def list_routes(self, status: Optional[str] = None) -> list[dict]:
        routes = await self.repo.get_all_routes(status)
        return [self._to_response(r) for r in routes]

    async def update_route(self, route_id: int, data: RouteRuleUpdate, user: str) -> Optional[dict]:
        update_data = data.model_dump(exclude_unset=True, exclude={"model_targets"})
        update_data["updated_by"] = user
        route = await self.repo.update_route(route_id, update_data)
        if not route:
            return None
        if data.model_targets is not None:
            await self.repo.set_route_targets(route_id, data.model_targets)
        return self._to_response(route)

    async def delete_route(self, route_id: int) -> bool:
        route = await self.repo.get_route_by_id(route_id)
        if not route:
            return False
        await self.repo.delete_route(route_id)
        return True

    async def sync_to_higress(self, route_id: int) -> bool:
        """Sync route config to Higress AI Gateway via Admin API."""
        route = await self.repo.get_route_by_id(route_id)
        if not route or route.status != "enabled":
            return False
        # TODO: Call Higress Admin API to sync route config
        return True

    def _to_response(self, route) -> dict:
        targets = []
        if hasattr(route, 'targets') and route.targets:
            targets = [
                {"model_id": t.model_id, "weight": t.weight, "priority": t.priority}
                for t in route.targets
            ]
        return {
            "id": route.id,
            "name": route.name,
            "path_pattern": route.path_pattern,
            "match_type": route.match_type,
            "strategy": route.strategy,
            "status": route.status,
            "priority": route.priority,
            "model_targets": targets,
            "created_at": route.created_at.isoformat() if route.created_at else None,
            "updated_at": route.updated_at.isoformat() if route.updated_at else None,
        }