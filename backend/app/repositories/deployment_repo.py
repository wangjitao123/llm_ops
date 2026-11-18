from typing import Optional
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.deployment import Deployment


class DeploymentRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> Deployment:
        deploy = Deployment(**data)
        self.db.add(deploy)
        await self.db.flush()
        return deploy

    async def get_by_id(self, deploy_id: int) -> Optional[Deployment]:
        result = await self.db.execute(
            select(Deployment).where(
                Deployment.id == deploy_id,
                Deployment.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        status: Optional[str] = None,
        deploy_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Deployment]:
        stmt = select(Deployment).where(Deployment.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Deployment.status == status)
        if deploy_type:
            stmt = stmt.where(Deployment.deploy_type == deploy_type)
        if search:
            stmt = stmt.where(Deployment.name.ilike(f"%{search}%"))
        stmt = stmt.order_by(Deployment.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, deploy_id: int, data: dict) -> Optional[Deployment]:
        stmt = (
            update(Deployment)
            .where(Deployment.id == deploy_id)
            .values(**data)
            .returning(Deployment)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, deploy_id: int) -> bool:
        from datetime import datetime, timezone
        result = await self.db.execute(
            update(Deployment)
            .where(Deployment.id == deploy_id)
            .values(deleted_at=datetime.now(timezone.utc))
            .returning(Deployment.id)
        )
        return result.scalar_one_or_none() is not None