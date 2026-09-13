import re
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.gateway_repo import GatewayRepo
from app.schemas.gateway import RouteRuleCreate, RouteRuleUpdate
from app.models.gateway import RouteRule, RouteRuleModel
from app.models.model import Model

# 限流配置缺行时的兜底默认值（与 rate_limit_config 列默认一致）
DEFAULT_GLOBAL_QPS = 5000
DEFAULT_KEY_QPS = 100

# 加权轮询序号（进程内计数器；多 worker 下各自累计，分布近似均匀）
_weighted_counters: dict[int, int] = {}


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
            await self.repo.db.refresh(route, ['targets'])

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
        # update…returning 返回的 ORM 对象未加载 targets 关系，显式刷新避免 MissingGreenlet
        if data.model_targets is not None:
            await self.repo.set_route_targets(route_id, data.model_targets)
        await self.repo.db.refresh(route, ['targets'])
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

    # ============================================================
    # 运行时路由分发（平台内置执行；未命中回退到"按 model 名直连"）
    # ============================================================

    @staticmethod
    def _path_matches(route, path: str) -> bool:
        """按路由配置的匹配方式判断请求路径是否命中。"""
        pattern = route.path_pattern or ""
        if route.match_type == "prefix":
            return path.startswith(pattern)
        if route.match_type == "regex":
            try:
                return re.search(pattern, path) is not None
            except re.error:
                return False
        return path == pattern  # exact（默认）

    def _route_candidates(
        self,
        route,
        model_name: str,
        exclude_model_id: Optional[int] = None,
    ) -> list:
        """路由目标过滤：目标模型在线、且 name 与客户端请求的 model 一致。"""
        out = []
        for t in route.targets or []:
            m = t.model if hasattr(t, "model") else None
            if m is None:
                continue
            if getattr(m, "deleted_at", None) is not None or m.status != "online":
                continue
            if m.name != model_name:
                continue
            if exclude_model_id is not None and m.id == exclude_model_id:
                continue
            out.append((t, m))
        out.sort(key=lambda x: (x[0].priority, x[0].id))
        return out

    def _pick_target(self, route, candidates: list):
        """按路由策略从目标集中选一台模型（入参已按 priority 排序）。"""
        if route.strategy == "weighted":
            total = sum(max(1, int(t.weight)) for t, _ in candidates)
            seq = _weighted_counters.get(route.id, 0)
            _weighted_counters[route.id] = seq + 1
            slot = seq % total
            for t, m in candidates:
                slot -= max(1, int(t.weight))
                if slot < 0:
                    return t, m
            return candidates[0][0], candidates[0][1]
        # single / active_standby：取优先级最高（priority 最小）的在线目标
        return candidates[0][0], candidates[0][1]

    async def route_model_for(
        self,
        path: str,
        model_name: str,
        exclude_model_id: Optional[int] = None,
    ) -> tuple[Optional[int], Optional[str], Optional[Model]]:
        """运行时路由选择：返回 (route_id, route_strategy, 选中的模型)。

        - 按 priority 顺序遍历启用路由，取第一个"路径命中且存在可用目标"的路由；
        - 目标 = 该路由下 name 与请求 model 一致且在线的模型实例；
        - 未命中任何路由/无可用目标 → (None, None, None)，调用方回退直连。
        """
        if not model_name:
            return (None, None, None)
        routes = await self.repo.get_enabled_routes_with_models()
        for route in routes:
            if not self._path_matches(route, path):
                continue
            candidates = self._route_candidates(route, model_name, exclude_model_id)
            if not candidates:
                continue
            _, model = self._pick_target(route, candidates)
            return (route.id, route.strategy, model)
        return (None, None, None)

    async def get_effective_qps_limits(self) -> tuple[int, int]:
        """读取限流配置：返回 (global_qps, default_key_qps)。"""
        cfg = await self.repo.get_rate_limit_config()
        if cfg is None:
            return (DEFAULT_GLOBAL_QPS, DEFAULT_KEY_QPS)
        return (
            cfg.global_qps or DEFAULT_GLOBAL_QPS,
            cfg.default_key_qps or DEFAULT_KEY_QPS,
        )

    def _to_response(self, route) -> dict:
        targets = []
        if hasattr(route, 'targets') and route.targets:
            for t in route.targets:
                try:
                    targets.append({
                        "model_id": t.model_id,
                        "weight": getattr(t, 'weight', 1) or 1,
                        "priority": getattr(t, 'priority', 0) or 0,
                    })
                except Exception:
                    targets.append({"model_id": 0, "weight": 1, "priority": 0})
        try:
            created_at = route.created_at.isoformat() if route.created_at else None
        except Exception:
            created_at = str(route.created_at) if route.created_at else None
        try:
            updated_at = route.updated_at.isoformat() if route.updated_at else None
        except Exception:
            updated_at = str(route.updated_at) if route.updated_at else None
        return {
            "id": route.id,
            "name": route.name or "",
            "path_pattern": route.path_pattern or "",
            "match_type": route.match_type or "exact",
            "strategy": route.strategy or "single",
            "status": route.status or "disabled",
            "priority": route.priority or 0,
            "model_targets": targets,
            "created_at": created_at,
            "updated_at": updated_at,
        }