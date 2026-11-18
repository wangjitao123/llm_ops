from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    app_name: str = "AI Gateway Platform"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/ai_platform"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Higress config
    higress_admin_api: str = "http://localhost:8080/api"

    # CORS：生产环境必须配置为明确的前端域名（逗号分隔），禁止使用 "*"（凭据模式不支持通配）
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 首次部署时自动建表（create_all）；已存在表不受影响。生产环境建议改用 Alembic 迁移。
    auto_create_tables: bool = False

    # API 侧数据库连接池（网关高并发关键参数）。
    # 流式请求期间会占连接，池容量应 >= 预期并发流数量，且不超过 Postgres max_connections。
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_recycle: int = 1800

    # 网关到上游模型的共享 HTTP 连接池（复用 TCP，避免每请求重新握手）
    http_pool_max_connections: int = 200
    http_pool_max_keepalive: int = 50
    http_connect_timeout: float = 10.0
    http_read_timeout: float = 300.0

    # Key last_used_at 落库降频窗口（秒）；0 表示每请求都写
    key_last_used_throttle_seconds: int = 60

    # ---- 模型部署（平台管理类型）----
    # 平台拉起推理容器所在的 Docker 网络（须与 api-server 同网络，网关才能按容器名直连）
    deploy_network: str = "llm-ops_backend"
    # 容器内推理引擎监听端口（vLLM/TGI 默认 8000）
    deploy_container_port: int = 8000
    # 宿主机对外发布端口区间（便于外部直连调试；网关内部走容器名）
    deploy_port_range_start: int = 31100
    deploy_port_range_end: int = 31299
    # 量化模型共享卷在容器内的挂载点
    deploy_models_mount: str = "/models"
    # 量化模型共享卷的 Docker 卷名（compose 项目名_卷名；不通则留空不挂载）
    deploy_models_volume: str = "llm-ops_quantized_models"
    # 推理引擎镜像
    deploy_vllm_image: str = "vllm/vllm-openai:v0.6.4.post1"
    deploy_tgi_image: str = "ghcr.io/huggingface/text-generation-inference:2.3.1"
    # 容器启动后等待就绪的最长时间（秒）
    deploy_ready_timeout: int = 600
    # GPU 采集缓存 TTL（秒）
    gpu_stats_ttl_seconds: int = 120

    # ---- 模型压测（perf-worker）----
    # 单任务并发上限（超过直接拒绝，防止打挂目标模型）
    perf_max_parallel: int = 500
    # 单任务请求数上限
    perf_max_number: int = 50000
    # 任务硬超时（秒），worker 侧强制中止
    perf_task_timeout: int = 1800
    # worker 同时执行任务数（与 docker compose --concurrency 保持一致）
    perf_worker_concurrency: int = 2
    # 进度回写间隔（秒）
    perf_progress_interval: int = 5
    # EvalScope 输出目录（容器内路径），HTML 报告存放于此，需挂持久卷
    perf_outputs_dir: str = "/app/perf_outputs"
    # 进度/中止标志在 Redis 的 key 前缀
    perf_redis_prefix: str = "perf"
    # 经网关压测时打向的地址（perf-worker 与 api-server 同网络，用容器名）
    perf_gateway_base_url: str = "http://llm-ops-api:8000/v1"
    # 压测模型白名单（逗号分隔的前缀，大小写不敏感）。
    # **留空 = 不限制**（平台上都是自建模型时的默认选择）。
    # 只有当你希望禁止对某些 provider 压测时，才填具体值，例如：
    #   PERF_TESTABLE_PROVIDER_PREFIX=local-,vllm
    perf_testable_provider_prefix: str = ""
    # 经网关压测时使用的平台 API Key（需在平台 Key 管理中创建；留空则禁止经网关压测）
    perf_gateway_api_key: str = ""

    # 开发模式直连登录开关：未接公司 SSO 前，允许 /dev-login 签发测试 JWT。
    # ⚠️ 生产环境对接 SSO 后必须设为 false！
    enable_dev_login: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()] or ["*"]


settings = Settings()