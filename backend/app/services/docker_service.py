"""Docker 容器编排：为「平台管理」类型的部署拉起推理引擎容器。

设计要点：
  * 客户端懒加载 —— 开发机/无 Docker 环境导入本模块不应报错；
  * 纯逻辑（命名、端口分配、启动参数拼装）抽成模块级函数，便于单测；
  * 容器同时加入 compose 的 backend 网络并用容器名寻址，网关走内网直连
    （避免绕宿主机 IP），同时把端口发布到宿主机便于外部直连调试。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_ENGINE_IMAGE_ATTR = {
    "vllm": "deploy_vllm_image",
    "tgi": "deploy_tgi_image",
}


class DeployError(RuntimeError):
    """部署过程中的可预期失败（镜像拉取失败、超时等），错误信息会展示给用户。"""


# ============================================================
# 纯逻辑（可单测，不依赖 docker 包）
# ============================================================

def build_container_name(deployment_id: int, engine: str, port: int) -> str:
    """容器名：dpl-{部署id}-{引擎}-{宿主机端口}，与端口一起保证唯一。"""
    return f"dpl-{deployment_id}-{(engine or 'vllm').lower()}-{port}"


def allocate_port(used: set[int], start: Optional[int] = None, end: Optional[int] = None) -> int:
    """在 [start, end] 区间内找一个未占用端口；区间耗尽抛 DeployError。"""
    lo = settings.deploy_port_range_start if start is None else start
    hi = settings.deploy_port_range_end if end is None else end
    for port in range(lo, hi + 1):
        if port not in used:
            return port
    raise DeployError(f"端口区间 {lo}-{hi} 已耗尽，请先在部署管理里清理无用部署")


def engine_image(engine: str) -> str:
    """按引擎取镜像地址。"""
    attr = _ENGINE_IMAGE_ATTR.get((engine or "vllm").lower())
    if not attr:
        raise DeployError(f"不支持的推理引擎: {engine}")
    return getattr(settings, attr)


def build_vllm_command(
    *,
    model_ref: str,
    served_model_name: str,
    api_key: Optional[str],
    max_model_len: int,
    tensor_parallel_size: int = 1,
    port: Optional[int] = None,
) -> list[str]:
    """拼装 vLLM OpenAI 兼容服务启动命令。

    model_ref 可以是 HF 模型 ID，也可以是容器内已挂载的量化模型目录。
    vLLM 会读取目录下 config.json 自动识别 GPTQ/AWQ，无需显式指定 --quantization。
    """
    cmd = [
        "--model", model_ref,
        "--served-model-name", served_model_name,
        "--host", "0.0.0.0",
        "--port", str(port or settings.deploy_container_port),
        "--max-model-len", str(int(max_model_len)),
    ]
    if tensor_parallel_size and int(tensor_parallel_size) > 1:
        cmd += ["--tensor-parallel-size", str(int(tensor_parallel_size))]
    if api_key:
        cmd += ["--api-key", api_key]
    return cmd


def container_endpoint(container_name: str) -> str:
    """网关访问容器用的内网地址（容器名解析，走 compose 网络）。"""
    return f"http://{container_name}:{settings.deploy_container_port}/v1"


def host_endpoint(host: str, port: int) -> str:
    """宿主机对外直连地址（便于调试与外部系统直连）。"""
    return f"http://{host}:{port}/v1"


# ============================================================
# Docker 客户端（懒加载）
# ============================================================

class DockerService:
    """薄封装 docker-py；无 docker 环境时所有操作抛 DeployError。"""

    def __init__(self) -> None:
        self._client = None

    # ---------- 客户端 ----------
    @property
    def client(self):
        if self._client is None:
            try:
                import docker  # 延迟导入：无 docker 包时导入本模块不报错
            except ImportError as e:  # pragma: no cover - 依赖环境
                raise DeployError(
                    "缺少 docker Python SDK（pip install docker），无法执行平台部署"
                ) from e
            try:
                self._client = docker.from_env()
            except Exception as e:
                raise DeployError(f"连接 Docker daemon 失败: {e}") from e
        return self._client

    def is_available(self) -> tuple[bool, Optional[str]]:
        """探测 Docker 是否可用，返回 (available, error)。"""
        try:
            self.client.ping()
            return True, None
        except DeployError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    # ---------- 容器操作 ----------
    def find_container(self, name: str):
        try:
            return self.client.containers.get(name)
        except Exception:
            return None

    def remove_container(self, name: str) -> bool:
        """删除容器（强制），不存在视为成功。"""
        c = self.find_container(name)
        if c is None:
            return False
        try:
            c.remove(force=True)
            return True
        except Exception as e:
            raise DeployError(f"删除容器 {name} 失败: {e}") from e

    def stop_container(self, name: str) -> bool:
        c = self.find_container(name)
        if c is None:
            return False
        try:
            c.stop(timeout=30)
            return True
        except Exception as e:
            raise DeployError(f"停止容器 {name} 失败: {e}") from e

    def used_ports(self) -> set[int]:
        """已发布到宿主机的端口集合。"""
        ports: set[int] = set()
        try:
            containers = self.client.containers.list(all=True)
        except Exception as e:
            raise DeployError(f"列出容器失败: {e}") from e
        for c in containers:
            for _container_port, bindings in (c.ports or {}).items():
                for b in bindings or []:
                    host_port = b.get("HostPort")
                    if host_port and str(host_port).isdigit():
                        ports.add(int(host_port))
        return ports

    # ---------- 运行容器 ----------
    def run_inference_container(
        self,
        *,
        image: str,
        name: str,
        command: list[str],
        host_port: int,
        gpu_count: int = 1,
        gpu_ids: Optional[list[int]] = None,
        models_volume: Optional[str] = None,
        environment: Optional[dict] = None,
        network: Optional[str] = None,
    ):
        """创建并启动推理容器。

        - GPU：指定 gpu_ids 时按 device_ids 精确分配，否则按 count 取前 N 张
        - 卷：把量化模型共享卷挂到 settings.deploy_models_mount
        - 网络：加入 compose 的 backend 网络，网关按容器名直连
        """
        import docker  # 局部导入，保持模块顶部无强依赖

        device_requests = None
        if gpu_count and int(gpu_count) > 0:
            kwargs = {"count": int(gpu_count), "capabilities": [["gpu"]]}
            if gpu_ids:
                kwargs = {"device_ids": [str(i) for i in gpu_ids], "capabilities": [["gpu"]]}
            device_requests = [docker.types.DeviceRequest(**kwargs)]

        volumes = {}
        if models_volume:
            volumes[models_volume] = {"bind": settings.deploy_models_mount, "mode": "ro"}

        try:
            container = self.client.containers.run(
                image=image,
                command=command,
                name=name,
                detach=True,
                remove=False,
                ports={f"{settings.deploy_container_port}/tcp": host_port},
                device_requests=device_requests,
                volumes=volumes or None,
                environment=environment or {},
                network=network or settings.deploy_network,
                ipc_mode="host",
                shm_size="16g",
            )
        except Exception as e:
            raise DeployError(f"创建容器失败: {e}") from e
        return container

    def container_logs(self, name: str, tail: int = 100) -> str:
        c = self.find_container(name)
        if c is None:
            return ""
        try:
            return c.logs(tail=tail).decode("utf-8", errors="ignore")
        except Exception:
            return ""


# 单例（懒加载）
docker_service = DockerService()
