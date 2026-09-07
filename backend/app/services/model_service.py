from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.model_repo import ModelRepo
from app.schemas.model import ModelCreate, ModelUpdate


class ModelService:
    def __init__(self, db: AsyncSession):
        self.repo = ModelRepo(db)

    async def create_model(self, data: ModelCreate, user: str) -> dict:
        model_data = data.model_dump(exclude={"api_key"})
        model_data["api_key_encrypted"] = data.api_key  # TODO: encrypt in production
        model_data["created_by"] = user
        model_data["updated_by"] = user
        model = await self.repo.create(model_data)
        
        # Create initial version
        version_data = {
            "model_id": model.id,
            "version": "1.0.0",
            "model_config_snapshot": data.model_config,
            "is_current": True,
            "change_log": "Initial version",
            "created_by": user,
        }
        await self.repo.create_version(version_data)
        
        return {"id": model.id, "name": model.name, "version": "1.0.0"}

    async def get_model(self, model_id: int) -> Optional[dict]:
        model = await self.repo.get_by_id(model_id)
        if not model:
            return None
        return self._to_response(model)

    async def list_models(self, provider: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        models = await self.repo.get_all(provider, status)
        return [self._to_response(m) for m in models]

    async def update_model(self, model_id: int, data: ModelUpdate, user: str) -> Optional[dict]:
        update_data = data.model_dump(exclude_unset=True, exclude={"api_key"})
        if data.api_key:
            update_data["api_key_encrypted"] = data.api_key
        update_data["updated_by"] = user
        
        model = await self.repo.update(model_id, update_data)
        if not model:
            return None
        
        # Create version record for significant changes
        version_data = {
            "model_id": model.id,
            "version": f"{model.version.split('.')[0]}.{int(model.version.split('.')[1]) + 1}.0",
            "model_config_snapshot": data.model_config,
            "is_current": True,
            "change_log": "Configuration updated",
            "created_by": user,
        }
        await self.repo.create_version(version_data)
        
        return self._to_response(model)

    async def update_status(self, model_id: int, status: str, user: str) -> Optional[dict]:
        model = await self.repo.update(model_id, {"status": status, "updated_by": user})
        if not model:
            return None
        return self._to_response(model)

    async def delete_model(self, model_id: int) -> bool:
        model = await self.repo.get_by_id(model_id)
        if not model:
            return False
        await self.repo.delete(model_id)
        return True

    async def get_versions(self, model_id: int) -> list[dict]:
        versions = await self.repo.get_versions(model_id)
        return [{"id": v.id, "version": v.version, "is_current": v.is_current, "change_log": v.change_log, "created_at": v.created_at.isoformat()} for v in versions]

    def _to_response(self, model) -> dict:
        return {
            "id": model.id,
            "name": model.name,
            "provider": model.provider,
            "version": model.version,
            "api_base_url": model.api_base_url,
            "qps_limit": model.qps_limit,
            "timeout_ms": model.timeout_ms,
            "weight": model.weight,
            "status": model.status,
            "health_check_url": model.health_check_url,
            "model_config": model.model_config,
            "description": model.description,
            "created_by": model.created_by,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "updated_at": model.updated_at.isoformat() if model.updated_at else None,
        }