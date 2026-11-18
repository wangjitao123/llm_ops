from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment import Deployment
from app.repositories.deployment_repo import DeploymentRepo
from app.repositories.model_repo import ModelRepo
from app.schemas.deployment import (
    DeploymentCreate,
    DeploymentUpdate,
    DeploymentResponse,
    GpuTopology,
    QuantizedModelItem,
)
from app.services import gpu_service

# 用户注册端点时常把完整路径贴进来（如 .../v1/chat/completions），
# 但平台内部统一按 api_base_url + "/chat/completions" 拼接，必须归一化，
# 否则网关会拼成 .../chat/completions/chat/completions 直接 404。
_ENDPOINT_SUFFIXES = ("/chat/completions", "/completions")


def normalize_endpoint(url: Optional[str]) -> str:
    """把用户填写的端点归一化成 API base（去掉 /chat/completions 等后缀）。"""
    if not url:
        return ""
    cleaned = url.strip().rstrip("/")
    for suffix in _ENDPOINT_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].rstrip("/")
            break
    return cleaned


class DeploymentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DeploymentRepo(db)
        self.model_repo = ModelRepo(db)

    def _to_response(self, deploy) -> dict:
        return DeploymentResponse.model_validate(deploy).model_dump()

    # ---------- CRUD ----------
    async def create_deployment(self, data: DeploymentCreate, user: str) -> dict:
        deploy_data = data.model_dump()
        deploy_data["created_by"] = user
        # 归一化端点：平台内部按 base + /chat/completions 拼接
        deploy_data["endpoint_url"] = normalize_endpoint(deploy_data.get("endpoint_url"))

        deploy = await self.repo.create(deploy_data)
        await self.db.commit()

        # 平台管理类型：立即派发部署任务
        if deploy.deploy_type == "managed":
            self._dispatch_deploy(deploy.id)

        return self._to_response(deploy)

    async def get_deployment(self, deploy_id: int) -> Optional[dict]:
        deploy = await self.repo.get_by_id(deploy_id)
        if not deploy:
            return None
        return self._to_response(deploy)

    async def list_deployments(
        self,
        status: Optional[str] = None,
        deploy_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        deploys = await self.repo.get_all(status, deploy_type, search)
        return [self._to_response(d) for d in deploys]

    async def update_deployment(self, deploy_id: int, data: DeploymentUpdate) -> Optional[dict]:
        update_data = {k: v for k, v in data.model_dump(exclude_none=True).items()}
        update_data["updated_at"] = datetime.now(timezone.utc)

        deploy = await self.repo.update(deploy_id, update_data)
        if not deploy:
            return None
        await self.db.commit()
        return self._to_response(deploy)

    async def delete_deployment(self, deploy_id: int) -> bool:
        deploy = await self.repo.get_by_id(deploy_id)
        if not deploy:
            return False

        # 1) 注销自动注册的模型（软删，保留历史用量数据）
        if deploy.registered_model_id:
            await self.model_repo.delete(deploy.registered_model_id)

        # 2) 平台管理类型：派发容器清理（api-server 无 Docker 权限，交给 worker）
        if deploy.deploy_type == "managed" and deploy.container_name:
            self._dispatch_remove(deploy.container_name)

        await self.db.commit()
        return await self.repo.delete(deploy_id)

    # ---------- 生命周期 ----------
    async def start_deployment(self, deploy_id: int) -> Optional[dict]:
        """启动部署（仅平台管理类型）。"""
        deploy = await self.repo.get_by_id(deploy_id)
        if not deploy:
            return None
        self._assert_managed(deploy, "启动")
        if deploy.status != "stopped":
            raise ValueError(f"当前状态 {deploy.status} 不允许启动")

        deploy = await self.repo.update(
            deploy_id,
            {
                "status": "deploying",
                "error_message": None,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.commit()
        self._dispatch_deploy(deploy_id)
        return self._to_response(deploy)

    async def stop_deployment(self, deploy_id: int) -> Optional[dict]:
        """停止部署（仅平台管理类型）。先把状态置 stopped 让 UI 立即响应。"""
        deploy = await self.repo.get_by_id(deploy_id)
        if not deploy:
            return None
        self._assert_managed(deploy, "停止")
        if deploy.status not in ("running", "deploying"):
            raise ValueError(f"当前状态 {deploy.status} 不允许停止")

        container_name = deploy.container_name
        deploy = await self.repo.update(
            deploy_id,
            {
                "status": "stopped",
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.commit()
        if container_name:
            self._dispatch_stop(container_name)
        return self._to_response(deploy)

    async def restart_deployment(self, deploy_id: int) -> Optional[dict]:
        """重启部署：先回收容器，再重新走一遍部署流程。"""
        deploy = await self.repo.get_by_id(deploy_id)
        if not deploy:
            return None
        self._assert_managed(deploy, "重启")
        if deploy.status not in ("running", "stopped", "failed"):
            raise ValueError(f"当前状态 {deploy.status} 不允许重启")

        container_name = deploy.container_name
        deploy = await self.repo.update(
            deploy_id,
            {
                "status": "deploying",
                "error_message": None,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.commit()
        if container_name:
            self._dispatch_remove(container_name)
        self._dispatch_deploy(deploy_id)
        return self._to_response(deploy)

    @staticmethod
    def _assert_managed(deploy, action: str) -> None:
        if deploy.deploy_type != "managed":
            raise ValueError(
                f"运行方式为 {deploy.deploy_type} 的部署不支持平台{action}，"
                "请在对应环境（conda/Docker）中手动管理"
            )

    # ---------- 任务派发（延迟导入，避免 API 进程强依赖 celery 配置） ----------
    @staticmethod
    def _dispatch_deploy(deploy_id: int) -> None:
        from app.tasks.deployment_tasks import deploy_container
        deploy_container.apply_async(args=[deploy_id], queue="deploy")

    @staticmethod
    def _dispatch_stop(container_name: str) -> None:
        from app.tasks.deployment_tasks import stop_container_task
        stop_container_task.apply_async(args=[container_name], queue="deploy")

    @staticmethod
    def _dispatch_remove(container_name: str) -> None:
        from app.tasks.deployment_tasks import remove_container_task
        remove_container_task.apply_async(args=[container_name], queue="deploy")

    # ---------- GPU 拓扑 ----------
    async def get_gpu_topology(self) -> dict:
        """获取 GPU 资源拓扑。

        数据来源优先级：Redis 缓存（由带 GPU 的 worker 采集）→ 本机现采 → 空。
        部署归属按 deployment.gpu_ids / gpu_count 反推。
        """
        deployment_map = await self._deployment_gpu_map()

        cached = await gpu_service.read_snapshot()
        if cached and cached.get("gpus"):
            return {
                "available": True,
                "source": f"cache({cached.get('source') or 'unknown'})",
                "error": None,
                "updated_at": cached.get("updated_at"),
                "gpus": [
                    g.model_dump()
                    for g in gpu_service.to_topology(cached["gpus"], deployment_map)
                ],
            }

        available, source, error, gpus = gpu_service.collect_local()
        if available:
            return {
                "available": True,
                "source": source,
                "error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "gpus": [g.model_dump() for g in gpu_service.to_topology(gpus, deployment_map)],
            }

        return {
            "available": False,
            "source": "none",
            "error": error,
            "updated_at": None,
            "gpus": [],
        }

    async def _deployment_gpu_map(self) -> dict[int, list[str]]:
        """构建 gpu_id → [部署名] 映射（仅统计运行中的平台管理部署）。"""
        result = await self.db.execute(
            select(Deployment).where(
                Deployment.deleted_at.is_(None),
                Deployment.status == "running",
            )
        )
        mapping: dict[int, list[str]] = {}
        for d in result.scalars().all():
            if d.gpu_ids:
                gpus = [int(i) for i in d.gpu_ids]
            else:
                gpus = list(range(int(d.gpu_count or 1)))
            for gid in gpus:
                mapping.setdefault(gid, []).append(d.name)
        return mapping

    # ---------- 供网关注入配置 ----------
    async def get_running_by_model_id(self, model_id: int) -> Optional[Deployment]:
        """按「自动注册的模型 id」反查在跑的部署（网关注入配置用）。"""
        result = await self.db.execute(
            select(Deployment).where(
                Deployment.registered_model_id == model_id,
                Deployment.deleted_at.is_(None),
                Deployment.status == "running",
            ).limit(1)
        )
        return result.scalar_one_or_none()

    # ---------- 量化模型列表 ----------
    async def get_quantized_models(self) -> list[QuantizedModelItem]:
        """获取已量化的模型列表（供新建部署选择）。"""
        from app.repositories.quantization_repo import QuantizationRepo

        q_repo = QuantizationRepo(self.db)
        tasks = await q_repo.get_all(status="completed")
        return [
            QuantizedModelItem(
                task_id=t.id,
                task_name=t.name,
                hf_model_id=t.hf_model_id,
                algorithm=t.algorithm,
                weight_bits=t.weight_bits,
                output_path=t.output_path or "",
                model_size_gb=None,
            )
            for t in tasks
        ]
