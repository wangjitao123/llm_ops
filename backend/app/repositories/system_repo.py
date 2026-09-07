from typing import Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system import SystemConfig, AlertRule, AlertLog, AuditLog, ModelEval, ExportTask, NotificationConfig


class SystemRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_config(self, config_key: str) -> Optional[SystemConfig]:
        result = await self.db.execute(
            select(SystemConfig).where(SystemConfig.config_key == config_key)
        )
        return result.scalar_one_or_none()

    async def get_configs_by_group(self, group: str) -> list[SystemConfig]:
        result = await self.db.execute(
            select(SystemConfig).where(SystemConfig.config_group == group)
        )
        return list(result.scalars().all())

    async def set_config(self, data: dict) -> SystemConfig:
        existing = await self.get_config(data["config_key"])
        if existing:
            stmt = update(SystemConfig).where(SystemConfig.config_key == data["config_key"]).values(**data).returning(SystemConfig)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        else:
            config = SystemConfig(**data)
            self.db.add(config)
            await self.db.flush()
            return config

    async def create_alert_rule(self, data: dict) -> AlertRule:
        rule = AlertRule(**data)
        self.db.add(rule)
        await self.db.flush()
        return rule

    async def get_alert_rules(self, enabled_only: bool = False) -> list[AlertRule]:
        stmt = select(AlertRule).where(AlertRule.deleted_at.is_(None))
        if enabled_only:
            stmt = stmt.where(AlertRule.enabled == True)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_audit_log(self, data: dict) -> AuditLog:
        log = AuditLog(**data)
        self.db.add(log)
        await self.db.flush()
        return log

    async def get_audit_logs(self, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        result = await self.db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def create_model_eval(self, data: dict) -> ModelEval:
        eval = ModelEval(**data)
        self.db.add(eval)
        await self.db.flush()
        return eval

    async def create_export_task(self, data: dict) -> ExportTask:
        task = ExportTask(**data)
        self.db.add(task)
        await self.db.flush()
        return task