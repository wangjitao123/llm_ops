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

    # 开发模式直连登录开关：未接公司 SSO 前，允许 /dev-login 签发测试 JWT。
    # ⚠️ 生产环境对接 SSO 后必须设为 false！
    enable_dev_login: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()] or ["*"]


settings = Settings()