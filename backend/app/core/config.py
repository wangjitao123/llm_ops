from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()] or ["*"]

    class Config:
        env_file = ".env"


settings = Settings()