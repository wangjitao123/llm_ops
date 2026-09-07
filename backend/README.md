# 大模型监测管理平台 — 后端服务

## 技术栈

- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL 16 + asyncpg
- Redis 7.x
- RabbitMQ + Celery
- Pydantic v2

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 启动服务
uvicorn app.main:app --reload --port 8000

# 启动 Celery Worker
celery -A app.tasks.worker worker -l info

# 运行测试
pytest
```

## 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── models.py     # 模型管理接口
│   │       ├── keys.py       # Key 管理接口
│   │       ├── tokens.py     # Token 统计接口
│   │       ├── gateway.py    # 网关管理接口
│   │       ├── finetune.py   # 微调管理接口
│   │       ├── compare.py    # 模型对比接口
│   │       └── system.py     # 系统管理接口
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py         # 配置管理
│   │   ├── security.py       # 安全/认证
│   │   ├── database.py       # 数据库连接
│   │   ├── redis.py          # Redis 客户端
│   │   └── dependencies.py   # 依赖注入
│   ├── models/
│   │   ├── __init__.py
│   │   ├── model.py          # 模型相关 ORM
│   │   ├── key.py            # Key 相关 ORM
│   │   ├── token.py          # Token 统计 ORM
│   │   ├── gateway.py        # 网关相关 ORM
│   │   ├── finetune.py       # 微调相关 ORM
│   │   ├── system.py         # 系统管理 ORM
│   │   └── base.py           # 基础 ORM 类
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── model.py          # 模型 Pydantic Schema
│   │   ├── key.py            # Key Schema
│   │   ├── token.py          # Token Schema
│   │   ├── gateway.py        # 网关 Schema
│   │   ├── finetune.py       # 微调 Schema
│   │   ├── system.py         # 系统 Schema
│   │   └── common.py         # 通用 Schema
│   ├── services/
│   │   ├── __init__.py
│   │   ├── model_service.py
│   │   ├── key_service.py
│   │   ├── token_service.py
│   │   ├── gateway_service.py
│   │   ├── finetune_service.py
│   │   ├── compare_service.py
│   │   └── system_service.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── model_repo.py
│   │   ├── key_repo.py
│   │   ├── token_repo.py
│   │   ├── gateway_repo.py
│   │   ├── finetune_repo.py
│   │   └── system_repo.py
│   └── tasks/
│       ├── __init__.py
│       ├── worker.py         # Celery 应用
│       ├── log_consumer.py   # 日志消费
│       ├── stats_aggregator.py # 统计聚合
│       └── alert_checker.py  # 预警检查
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_keys.py
│   ├── test_tokens.py
│   └── test_system.py
├── alembic/                  # 数据库迁移
├── Dockerfile
└── pyproject.toml
```