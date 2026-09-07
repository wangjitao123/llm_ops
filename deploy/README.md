# 大模型监测管理平台 — 部署指南（单机 Linux + Docker Compose + Higress）

> 目标环境：一台 Linux 服务器（Ubuntu 20.04+/CentOS 7.9+，2C8G 起步）
> 交付内容：`docker-compose.yml`（平台服务）+ `docker-compose.higress.yml`（Higress 接入说明）

---

## 0. 架构总览

```
浏览器
  │  http://<服务器IP>:80
  ▼
nginx (web 容器，前端静态资源 + /api 反代)
  │
  ├──► api-server:8000 (FastAPI) ──► postgres / redis / rabbitmq
  │              │
  │              └──► celery-worker / celery-beat (异步任务)
  │
  └──► [可选] Higress Gateway:8080 ──► 外部模型 API (DeepSeek/OpenAI...)
```

---

## 1. 服务器准备

```bash
# 1.1 安装 Docker（如已安装可跳过）
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker

# 1.2 安装 Docker Compose 插件（新版 docker 自带，检查）
docker compose version
# 若提示无 compose 插件：
#   sudo apt install docker-compose-plugin

# 1.3 验证
docker run --rm hello-world
```

## 2. 获取代码并准备配置

```bash
# 2.1 克隆项目到服务器
git clone https://github.com/wangjitao123/llm_ops_platform.git
cd llm_ops_platform/deploy

# 2.2 生成 .env 并修改所有密码/密钥！
cp .env.example .env
vim .env
# 必改项：
#   POSTGRES_PASSWORD / REDIS_PASSWORD / RABBITMQ_PASSWORD
#   SECRET_KEY   ← 生成：openssl rand -hex 32
```

## 3. 启动平台服务

```bash
cd deploy
docker compose up -d --build

# 查看状态（应全部 running / healthy）
docker compose ps

# 查看日志
docker compose logs -f api-server
```

**启动后验证**：

| 项 | 地址 | 预期 |
|----|------|------|
| 前端管理台 | `http://<IP>/` | 出现登录页 |
| 后端健康检查 | `http://<IP>:8000/health` | `{"status":"ok","version":"0.1.0"}` |
| API 文档 | `http://<IP>:8000/docs` | Swagger UI |
| RabbitMQ 管理台 | `http://<IP>:15672` | 输入 RABBITMQ_USER/PASSWORD |

> **首次部署自动建表**：api-server 容器启动命令先执行 `python -m app.core.init_db`，
> 然后 `AUTO_CREATE_TABLES=true` 兜底 create_all，业务表会自动创建。
> 注：`api_request_log` 的分区结构属生产优化项，当前先按普通表创建；
> 生产高吞吐可另行执行 `docs/概要设计/数据库设计/sql/01-create-tables.sql` 的分区 DDL。

## 4. 接入 Higress AI 网关（可选，推荐二期）

Higress 作为 AI 网关核心（统一模型出口、Key 鉴权、限流、协议转换）推荐独立编排。
**方式 A — 官方 standalone（推荐）**：

```bash
# 克隆官方 standalone 模板（含 nacos/controller/gateway/console 完整 compose）
git clone https://github.com/higress-group/higress-standalone.git
cd higress-standalone
# 按其 README 修改后启动，console 默认 http://<IP>:8001

# 关键：把 Higress 网关与本平台网络打通（二选一）
# A. 加入本平台网络
docker network connect llm_ops_platform_default higress-gateway   # 注意实际网络名以 `docker network ls` 为准
# B. 或让本平台网络加入 higress 网络（在部署文档网络配置里互连）
```

在 Higress Console 中配置路由：

| 场景 | 路由 | 上游 |
|------|------|------|
| 管理台转发 | `Host=域名 or IP`，`Path=/` | `http://llm-ops-web:80` |
| 平台 API 转发 | `Path=/api/v1/*` | `http://llm-ops-api:8000` |
| 模型出口示例 | AI 路由 model=deepseek-chat | `https://api.deepseek.com` |
| 模型出口示例 | AI 路由 model=gpt-4o | `https://api.openai.com` |

配置详情参考：
- [Higress Docker Compose 独立部署](https://higress.cn/docs/latest/ops/deploy-by-docker-compose/)
- [Higress Standalone 仓库](https://github.com/higress-group/higress-standalone)
- [本项目技术方案-网关设计](docs/技术方案/大模型监测管理平台-技术方案.md)

## 5. 日常运维

```bash
# 重启服务
docker compose restart api-server

# 滚动更新代码
git pull
docker compose up -d --build

# 查看资源占用
docker stats

# 数据备份（重要！）
docker exec llm-ops-postgres pg_dump -U llmops ai_platform > backup_$(date +%F).sql

# 恢复
cat backup_xxx.sql | docker exec -i llm-ops-postgres psql -U llmops ai_platform
```

## 6. 故障排查

| 症状 | 排查方法 |
|------|----------|
| 前端 502/超时 | `docker compose logs web`；确认 api-server healthy；确认 web 容器可 `curl http://api-server:8000/health` |
| 后端连不上库 | `docker compose logs api-server`；确认 postgres healthy；检查 `.env` 密码与 compose 引用一致 |
| 端口冲突 | `sudo ss -tlnp` 查看 80/8000/15672 占用，改 `.env` 中 `WEB_PORT` 等 |
| 时区/中文乱码 | 容器已设 `TZ=Asia/Shanghai`；前端 Nginx 已设 UTF-8 |

## 7. 安全清单（上线前必读）

- [ ] `.env` 中所有默认密码已替换；SECRET_KEY 已改
- [ ] `CORS_ORIGINS` 已设为你的前端域名（如 `https://ai.example.com`），**不要**用 `*`
- [ ] 服务器防火墙仅开放 80（前端）；8000/15672 管理端口不对外开放
- [ ] 对接真实 SSO 前，登录页处于"开发直连"模式，注意勿暴露公网
- [ ] Higress 上游模型 Key 存储在模型配置中，建议二次加密（后端已预留 `api_key_encrypted`）
- [ ] 定期 `pg_dump` 备份，建议挂 cron

---

## 附：服务端口清单

| 服务 | 容器内端口 | 宿主映射（默认） | 说明 |
|------|-----------|------------------|------|
| web (nginx) | 80 | 80 | 前端入口 |
| api-server | 8000 | 8000 | FastAPI（调试用，可关） |
| postgres | 5432 | 无（仅内网） | 数据库 |
| redis | 6379 | 无（仅内网） | 缓存/限流 |
| rabbitmq | 5672 / 15672 | 15672 | 消息队列/管理台 |
| higress (可选) | 80 / 8001 | 8080 / 8001 | AI 网关 / 控制台 |
