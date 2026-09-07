import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.key_repo import KeyRepo, ApplicationRepo
from app.schemas.key import KeyCreate, KeyUpdate


class KeyService:
    KEY_PREFIX = "sk-"

    def __init__(self, db: AsyncSession):
        self.repo = KeyRepo(db)

    def _generate_key(self) -> tuple[str, str, str]:
        raw_key = self.KEY_PREFIX + secrets.token_hex(24)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:10]
        return raw_key, key_hash, key_prefix

    async def create_key(self, data: KeyCreate, user: str) -> dict:
        raw_key, key_hash, key_prefix = self._generate_key()
        key_data = {
            "name": data.name,
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "application_id": data.application_id,
            "created_by": user,
            "qps_limit": data.qps_limit,
            "rpm_limit": data.rpm_limit,
            "rpd_limit": data.rpd_limit,
            "token_quota": data.token_quota,
            "expires_at": data.expires_at,
        }
        key = await self.repo.create_key(key_data)
        
        if data.model_ids:
            await self.repo.set_model_permissions(key.id, data.model_ids)
        
        return {
            "id": key.id,
            "name": key.name,
            "key_full": raw_key,  # Only shown once
            "key_prefix": key.key_prefix,
            "status": key.status,
            "created_at": key.created_at.isoformat(),
        }

    async def get_key(self, key_id: int) -> Optional[dict]:
        key = await self.repo.get_by_id(key_id)
        if not key:
            return None
        return await self._to_response(key)

    async def list_keys(self, status: Optional[str] = None) -> list[dict]:
        keys = await self.repo.get_all(status)
        return [await self._to_response(k) for k in keys]

    async def update_key(self, key_id: int, data: KeyUpdate, user: str) -> Optional[dict]:
        # 注意：app_key 表只有 created_by 审计列，没有 updated_by；不能写入
        update_data = data.model_dump(exclude_unset=True, exclude={"model_ids"})
        if data.model_ids is not None:
            await self.repo.set_model_permissions(key_id, data.model_ids)
        key = await self.repo.update_key(key_id, update_data)
        if not key:
            return None
        return await self._to_response(key)

    async def delete_key(self, key_id: int) -> bool:
        key = await self.repo.get_by_id(key_id)
        if not key:
            return False
        await self.repo.delete_key(key_id)
        return True

    async def verify_key(self, key_hash: str) -> Optional[dict]:
        key = await self.repo.get_by_key_hash(key_hash)
        if not key or key.status != "active" or key.deleted_at:
            return None
        if key.expires_at and key.expires_at < datetime.now(timezone.utc):
            await self.repo.update_key(key.id, {"status": "expired"})
            return None
        return {"id": key.id, "qps_limit": key.qps_limit, "token_quota": key.token_quota}

    async def _to_response(self, key) -> dict:
        perms = await self.repo.get_model_permissions(key.id)
        # AppKeyModel 无 deleted_at 时 hasattr 判断保持兼容
        model_ids = []
        for p in perms:
            if hasattr(p, "deleted_at") and p.deleted_at:
                continue
            model_ids.append(p.model_id)
        return {
            "id": key.id,
            "name": key.name,
            "key_prefix": key.key_prefix,
            "application_id": key.application_id,
            "qps_limit": key.qps_limit,
            "rpm_limit": key.rpm_limit,
            "rpd_limit": key.rpd_limit,
            "token_quota": key.token_quota,
            "token_used": key.token_used,
            "model_ids": model_ids,
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
            "status": key.status,
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
            "created_at": key.created_at.isoformat() if key.created_at else None,
            "updated_at": key.updated_at.isoformat() if key.updated_at else None,
        }


class ApplicationService:
    def __init__(self, db: AsyncSession):
        self.repo = ApplicationRepo(db)

    async def create(self, name: str, description: str | None, user: str) -> dict:
        app = await self.repo.create({"name": name, "description": description, "created_by": user, "updated_by": user})
        return {"id": app.id, "name": app.name, "description": app.description, "created_at": app.created_at.isoformat()}

    async def list_all(self) -> list[dict]:
        apps = await self.repo.get_all()
        return [{"id": a.id, "name": a.name, "description": a.description, "created_at": a.created_at.isoformat()} for a in apps]