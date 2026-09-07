"""模型汇总导出：确保 SQLAlchemy metadata 能发现全部表（供 create_all / Alembic 使用）。"""

from app.core.database import Base

# 导入各业务模型模块，注册到 Base.metadata
from app.models.model import Model, ModelVersion, ModelHeartbeat
from app.models.key import Application, AppKey, AppKeyModel
from app.models.token import ApiRequestLog, TokenStatsHourly, TokenStatsDaily
from app.models.gateway import RouteRule, RouteRuleModel, RateLimitConfig
from app.models.finetune import Dataset, DatasetVersion, FinetuneTask, FinetuneEval
from app.models.system import (
    SystemConfig,
    AlertRule,
    AlertLog,
    NotificationConfig,
    AuditLog,
    ModelEval,
    ExportTask,
)

__all__ = [
    "Base",
    "Model",
    "ModelVersion",
    "ModelHeartbeat",
    "Application",
    "AppKey",
    "AppKeyModel",
    "ApiRequestLog",
    "TokenStatsHourly",
    "TokenStatsDaily",
    "RouteRule",
    "RouteRuleModel",
    "RateLimitConfig",
    "Dataset",
    "DatasetVersion",
    "FinetuneTask",
    "FinetuneEval",
    "SystemConfig",
    "AlertRule",
    "AlertLog",
    "NotificationConfig",
    "AuditLog",
    "ModelEval",
    "ExportTask",
]
