from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.system_repo import SystemRepo
from app.schemas.system import SystemConfigCreate, AlertRuleCreate


class SystemService:
    def __init__(self, db: AsyncSession):
        self.repo = SystemRepo(db)

    async def get_config(self, config_key: str) -> Optional[dict]:
        config = await self.repo.get_config(config_key)
        if not config:
            return None
        return {"config_key": config.config_key, "config_value": config.config_value, "config_group": config.config_group, "description": config.description}

    async def get_configs_by_group(self, group: str) -> list[dict]:
        configs = await self.repo.get_configs_by_group(group)
        return [{"config_key": c.config_key, "config_value": c.config_value, "config_group": c.config_group} for c in configs]

    async def set_config(self, data: SystemConfigCreate, user: str) -> dict:
        config_data = {
            "config_key": data.config_key,
            "config_value": data.config_value,
            "config_group": data.config_group,
            "description": data.description,
            "encrypted": data.encrypted,
            "created_by": user,
            "updated_by": user,
        }
        config = await self.repo.set_config(config_data)
        return {"config_key": config.config_key, "config_group": config.config_group, "updated_at": config.updated_at.isoformat()}

    async def create_alert_rule(self, data: AlertRuleCreate, user: str) -> dict:
        rule_data = data.model_dump()
        rule_data["created_by"] = user
        rule_data["updated_by"] = user
        rule = await self.repo.create_alert_rule(rule_data)
        return {"id": rule.id, "name": rule.name, "metric_type": rule.metric_type, "threshold_value": rule.threshold_value, "enabled": rule.enabled}

    async def list_alert_rules(self) -> list[dict]:
        rules = await self.repo.get_alert_rules()
        return [{"id": r.id, "name": r.name, "metric_type": r.metric_type, "threshold_value": r.threshold_value, "enabled": r.enabled, "created_at": r.created_at.isoformat()} for r in rules]

    async def get_audit_logs(self, page: int = 1, size: int = 20) -> dict:
        offset = (page - 1) * size
        logs = await self.repo.get_audit_logs(limit=size, offset=offset)
        items = [{"id": l.id, "user_id": l.user_id, "action_type": l.action_type, "action_detail": l.action_detail, "target_type": l.target_type, "target_id": l.target_id, "client_ip": l.client_ip, "result": l.result, "created_at": l.created_at.isoformat()} for l in logs]
        return {"items": items, "page": page, "size": size, "total": len(items)}

    async def create_audit_log(self, user_id: str, action_type: str, action_detail: str, target_type: str | None = None, target_id: int | None = None, client_ip: str | None = None, result: str = "success") -> None:
        await self.repo.create_audit_log({
            "user_id": user_id, "action_type": action_type, "action_detail": action_detail,
            "target_type": target_type, "target_id": target_id, "client_ip": client_ip, "result": result,
        })