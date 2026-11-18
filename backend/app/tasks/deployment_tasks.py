"""模型部署模块 — Celery 异步任务。

包含三件事：
  1. health_check_all  —— 周期性健康检查所有运行中的端点（Beat 每 30s）
  2. deploy_container  —— 平台管理类型：拉起 vLLM 容器并等就绪 → 自动注册模型
  3. collect_gpu_stats —— 采集 GPU 显存占用写 Redis（跑在带 GPU 的队列上）

注意：本模块所有 DB 操作必须走 task_async_session（NullPool），
否则跨事件循环复用连接会报 "attached to a different loop"。
"""
import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import task_async_session as async_session
from app.models.deployment import Deployment
from app.repositories.deployment_repo import DeploymentRepo
from app.repositories.model_repo import ModelRepo
from app.services import gpu_service
from app.services.docker_service import (
    DeployError,
    allocate_port,
    build_container_name,
    build_vllm_command,
    container_endpoint,
    docker_service,
    engine_image,
)
from app.tasks.worker import celery_app

logger = logging.getLogger(__name__)


# ============================================================
# 纯逻辑（供单测）
# ============================================================

def generate_model_api_key() -> str:
    """给部署出来的模型生成一把 API Key（同时传给 vLLM 的 --api-key）。"""
    return "sk-dpl-" + secrets.token_urlsafe(32)


def build_model_payload(
    *,
    name: str,
    endpoint_url: str,
    api_key: str,
    qps_limit: int,
    hf_model_id: Optional[str],
    engine: Optional[str],
    operator: str,
) -> dict:
    """构造「自动注册到模型管理」所需的 model 表字段。"""
    return {
        "name": name,
        "provider": f"local-{engine or 'vllm'}",
        "version": "1.0.0",
        "api_base_url": endpoint_url,
        "api_key_encrypted": api_key,
        "qps_limit": int(qps_limit or 100),
        "timeout_ms": 120000,
        "weight": 1,
        "status": "online",
        "health_check_url": f"{endpoint_url.rstrip('/')}/models",
        "model_config": {"hf_model_id": hf_model_id, "engine": engine},
        "description": "由模型部署模块自动注册",
        "created_by": operator or "system",
        "updated_by": operator or "system",
    }


def resolve_model_ref(model_path: Optional[str], hf_model_id: Optional[str]) -> str:
    """解析推理引擎要加载的模型引用。

    量化产出路径（如 /models/qwen-7b-gptq）与容器内挂载点一致，可直接使用；
    否则退化为 HuggingFace 模型 ID。
    """
    if model_path:
        path = model_path.strip()
        if path.startswith(settings.deploy_models_mount):
            return path
        return f"{settings.deploy_models_mount.rstrip('/')}/{path.lstrip('/')}"
    if hf_model_id:
        return hf_model_id.strip()
    raise DeployError("缺少模型来源：既没有量化产出路径，也没有 HuggingFace 模型 ID")


def gpus_for_deployment(deploy: Deployment) -> list[int]:
    """推断该部署占用的 GPU 编号（用于拓扑图归属展示）。"""
    if deploy.gpu_ids:
        return [int(i) for i in deploy.gpu_ids]
    return list(range(int(deploy.gpu_count or 1)))


# ============================================================
# 1. 健康检查
# ============================================================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def health_check_all(self):
    """对所有运行中的部署执行健康检查（Celery Beat 每 30 秒调度一次）。"""
    try:
        asyncio.run(_do_health_checks())
    except Exception as e:  # noqa: BLE001
        logger.error("健康检查失败: %s", e)
        raise self.retry(exc=e)


async def _do_health_checks():
    async with async_session() as session:
        repo = DeploymentRepo(session)
        deploys = await repo.get_all(status="running")
        if not deploys:
            return

        async with httpx.AsyncClient(timeout=10) as client:
            for deploy in deploys:
                if not deploy.health_check_enabled:
                    continue

                base = (deploy.endpoint_url or "").rstrip("/")
                healthy = False
                status_code = 0
                latency_ms = 0
                error_msg: Optional[str] = None

                if base:
                    # 兼容两种上游：OpenAI 兼容入口 /models，或裸引擎 /health
                    for path in ("/models", "/health"):
                        try:
                            resp = await client.get(f"{base}{path}")
                            status_code = resp.status_code
                            latency_ms = int(resp.elapsed.total_seconds() * 1000)
                            healthy = resp.status_code == 200
                            if healthy:
                                break
                        except Exception as e:  # noqa: BLE001 - 记录任意连接异常
                            error_msg = str(e)
                else:
                    error_msg = "endpoint_url 为空"

                await session.execute(
                    text(
                        "INSERT INTO deployment_health_log "
                        "(deployment_id, status_code, latency_ms, is_healthy, error_message, checked_at) "
                        "VALUES (:deployment_id, :status_code, :latency_ms, :is_healthy, :error_message, :checked_at)"
                    ),
                    {
                        "deployment_id": deploy.id,
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                        "is_healthy": healthy,
                        "error_message": error_msg,
                        "checked_at": datetime.now(timezone.utc),
                    },
                )

                if healthy:
                    continue

                fail_count = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM deployment_health_log "
                            "WHERE deployment_id = :did AND is_healthy = FALSE "
                            "AND checked_at > NOW() - INTERVAL '5 minutes'"
                        ),
                        {"did": deploy.id},
                    )
                ).scalar()

                if fail_count and int(fail_count) >= 3:
                    logger.warning(
                        "部署 %s 连续 %s 次健康检查失败，标记为异常", deploy.name, fail_count
                    )
                    await repo.update(
                        deploy.id,
                        {
                            "status": "failed",
                            "error_message": f"连续 {fail_count} 次健康检查失败",
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )

        await session.commit()


# ============================================================
# 2. 部署容器
# ============================================================

@celery_app.task(bind=True, max_retries=0)
def deploy_container(self, deployment_id: int):
    """异步部署推理容器（失败不自动重试，避免反复拉镜像烧资源）。"""
    try:
        asyncio.run(_do_deploy(deployment_id))
    except Exception as e:  # noqa: BLE001 - 状态已由内部处理，这里只兜底记日志
        logger.error("部署 %s 任务异常: %s", deployment_id, e)


async def _wait_ready(endpoint: str, timeout: int) -> tuple[bool, str]:
    """轮询等待推理服务就绪；返回 (ready, 最后错误)。"""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last_error = "未开始探测"
    async with httpx.AsyncClient(timeout=5) as client:
        while loop.time() < deadline:
            try:
                resp = await client.get(f"{endpoint.rstrip('/')}/models")
                if resp.status_code == 200:
                    return True, "ok"
                last_error = f"HTTP {resp.status_code}"
            except Exception as e:  # noqa: BLE001 - 启动期连不上属正常
                last_error = str(e)
            await asyncio.sleep(5)
    return False, f"等待就绪超时（{timeout}s），最后错误: {last_error}"


async def _do_deploy(deployment_id: int):
    """执行部署：拉起容器 → 等就绪 → 更新状态 → 自动注册到模型管理。"""
    async with async_session() as session:
        repo = DeploymentRepo(session)
        model_repo = ModelRepo(session)
        deploy = await repo.get_by_id(deployment_id)
        if deploy is None:
            logger.error("部署 %d 不存在", deployment_id)
            return
        if deploy.status != "deploying":
            logger.warning("部署 %d 状态 %s 不允许部署", deployment_id, deploy.status)
            return

        container_name: Optional[str] = None
        try:
            if (deploy.engine or "vllm") != "vllm":
                raise DeployError(
                    f"暂只支持 vLLM 自动部署（当前 engine={deploy.engine}）。"
                    "TGI/SGLang 请先用「注册已有端点」接入"
                )

            available, err = docker_service.is_available()
            if not available:
                raise DeployError(f"Docker 不可用: {err}")

            # 清理该部署遗留的旧容器（重启/重试场景）：以 DB 里记录的容器名为准
            if deploy.container_name:
                docker_service.remove_container(deploy.container_name)

            model_ref = resolve_model_ref(deploy.model_path, deploy.hf_model_id)
            api_key = generate_model_api_key()
            port = allocate_port(docker_service.used_ports())
            container_name = build_container_name(deploy.id, deploy.engine, port)

            # 清理同名残留（上一次失败留下的容器）
            docker_service.remove_container(container_name)

            command = build_vllm_command(
                model_ref=model_ref,
                served_model_name=deploy.name,
                api_key=api_key,
                max_model_len=deploy.max_input_tokens or 4096,
                tensor_parallel_size=deploy.gpu_count or 1,
            )

            logger.info("启动容器 %s: %s", container_name, " ".join(command))
            docker_service.run_inference_container(
                image=engine_image(deploy.engine),
                name=container_name,
                command=command,
                host_port=port,
                gpu_count=deploy.gpu_count or 1,
                gpu_ids=deploy.gpu_ids,
                models_volume=settings.deploy_models_volume or None,
                environment={"HF_HOME": "/models/.hf", "TZ": "Asia/Shanghai"},
            )

            endpoint = container_endpoint(container_name)
            ready, reason = await _wait_ready(endpoint, settings.deploy_ready_timeout)

            if not ready:
                logs_tail = docker_service.container_logs(container_name, tail=40)
                raise DeployError(f"容器未就绪：{reason}\n--- 容器日志 ---\n{logs_tail}")

            update_data = {
                "status": "running",
                "endpoint_url": endpoint,
                "container_name": container_name,
                "host_port": port,
                "error_message": None,
                "updated_at": datetime.now(timezone.utc),
            }

            if deploy.auto_register:
                payload = build_model_payload(
                    name=deploy.name,
                    endpoint_url=endpoint,
                    api_key=api_key,
                    qps_limit=deploy.max_concurrency,
                    hf_model_id=deploy.hf_model_id,
                    engine=deploy.engine,
                    operator=deploy.created_by,
                )
                model = await model_repo.create(payload)
                update_data["registered_model_id"] = model.id
                logger.info("部署 %s 已注册为模型 #%s", deploy.name, model.id)

            await repo.update(deploy.id, update_data)
            await session.commit()
            logger.info("部署 %s 完成，端点 %s", deploy.name, endpoint)

        except Exception as e:  # noqa: BLE001 - 任何失败都要落状态给用户看
            logger.error("部署 %s 失败: %s", deployment_id, e)
            if container_name:
                try:
                    docker_service.remove_container(container_name)
                except Exception:  # noqa: BLE001
                    logger.warning("清理容器 %s 失败", container_name, exc_info=True)
            await repo.update(
                deploy.id,
                {
                    "status": "failed",
                    "error_message": str(e)[:4000],
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await session.commit()


# ============================================================
# 3. 容器生命周期（停止 / 删除），供 API 侧异步派发
# ============================================================

@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def stop_container_task(self, container_name: str):
    """停止容器（API 侧已先把状态置为 stopped，这里只做资源回收）。"""
    try:
        docker_service.stop_container(container_name)
        logger.info("容器 %s 已停止", container_name)
    except Exception as e:  # noqa: BLE001
        logger.warning("停止容器 %s 失败: %s", container_name, e)
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def remove_container_task(self, container_name: str):
    """删除容器（含数据卷之外的一切运行时资源）。"""
    try:
        docker_service.remove_container(container_name)
        logger.info("容器 %s 已删除", container_name)
    except Exception as e:  # noqa: BLE001
        logger.warning("删除容器 %s 失败: %s", container_name, e)
        raise self.retry(exc=e)


# ============================================================
# 4. GPU 采集（跑在带 GPU 的 worker 队列上）
# ============================================================

@celery_app.task(bind=True, max_retries=0)
def collect_gpu_stats(self):
    """采集本机 GPU 显存占用并写 Redis，供 API 只读消费。"""
    try:
        available, source, error, gpus = gpu_service.collect_local()
        if not available:
            logger.debug("GPU 采集跳过: %s", error)
            return
        asyncio.run(gpu_service.publish_snapshot(gpus, source))
    except Exception as e:  # noqa: BLE001
        logger.warning("GPU 采集失败: %s", e)
