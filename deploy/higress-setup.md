# Higress AI 网关接入 — 服务器操作手册（单机 Docker Compose）

> 目标：让"应用带平台 Key → 走平台地址 → 转发到本地/自建模型（无 Key）"可用。
> 前置：本平台主服务已跑通（`docker compose ps` 全 healthy）。
> 参考：<https://higress.cn/docs/latest/ops/deploy-by-docker-compose/>、<https://github.com/higress-group/higress-standalone>

---

## 0. 先确认：本地模型服务是哪种 OpenAI 兼容实现

本手册适用 **vLLM / OneAPI / LiteLLM / Ollama / Xinference** 等任意提供
`POST /v1/chat/completions` 的服务。先记录它的：

```bash
# 用 OpenAI 兼容地址测试（把端口/路径换成实际的）
curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"<你的模型名>","messages":[{"role":"user","content":"hi"}],"max_tokens":8}'
```

记下：**服务地址**（如 `http://127.0.0.1:8001`）、**OpenAI 兼容路径**（通常 `/v1`）、**模型名**。

> 💡 **平台已内置 OpenAI 兼容入口**：只要 api-server 在跑，
> `POST {平台}/v1/chat/completions` 就能带平台 Key 直接转发到模型（无需先上 Higress）。
> 想先验证链路，直接看《docs/api/模型入口对接指南.md》，Higress 是生产网关的强化层。

## 第 1 步：在管理台登记本地模型（平台内置入口已可用）

1. 模型管理 → 添加模型：
   - **模型名称**：应用调用时的 model 名（如 `local-qwen`）
   - **提供商**：选 local / 自定义
   - **API 地址**：本地模型 OpenAI 兼容基址，如 `http://10.51.13.7:8001/v1`
   - **API Key**：**留空**（本地模型无 Key）
2. Key 管理 → 新建 Key（给应用用），可选绑定该模型
3. 验证：

```bash
curl http://10.51.13.7:8085/v1/chat/completions \
  -H "Authorization: Bearer sk-你平台发的key" \
  -H "Content-Type: application/json" \
  -d '{"model":"local-qwen","messages":[{"role":"user","content":"你好"}],"max_tokens":16}'
```

> 若 8085 的 nginx 未转发 `/v1/`，可先用 8000 直连 api-server 验证，
> 或按《模型入口对接指南》给 nginx 加 location 后重建 web。

## 第 2 步：启动 Higress standalone（可选，生产网关）

```bash
cd /data
git clone https://github.com/higress-group/higress-standalone.git
cd higress-standalone
# 按官方 README 调整（.env / compose），然后：
docker compose up -d
docker compose ps   # nacos / higress-controller / higress-gateway / higress-console 均 Up
```

> ⚠️ 一律以官方 README 为准，别照抄网络旧教程。

## 第 3 步：打通 Higress 与本平台网络

```bash
docker network ls | grep higress
docker network connect llm-ops_frontend higress-gateway
docker network connect llm-ops_backend  higress-gateway
docker exec higress-gateway curl -s http://llm-ops-api:8000/health || \
  docker exec higress-gateway wget -qO- http://llm-ops-api:8000/health
# 期望 {"status":"ok","version":"0.1.0"}
```

## 第 4 步：Console 配置 Provider 与 AI 路由

Higress Console 默认 `http://<IP>:8001`（以官方为准）。

**4.1 AI Provider（指到你的本地模型服务）**

| 配置项 | 值 |
|--------|-----|
| 名称 | `local-llm` |
| 协议/类型 | OpenAI（兼容） |
| 上游地址 | `http://<宿主机内网IP>:8001`（Higress 容器访问宿主用内网 IP，勿用 127.0.0.1） |
| 模型列表 | 你本地模型名 |
| API Key | 留空 |

**4.2 AI 路由（对外入口）**：域名/IP、路径 `/v1/chat/completions` → 目标 `local-llm`。

**4.3 验证**：

```bash
curl http://<IP>:<网关端口>/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"<本地模型名>","messages":[{"role":"user","content":"hi"}]}'
```

## 第 5 步：接入平台 Key 鉴权

平台已提供网关校验端点：`POST /api/v1/gateway/verify-key`（请求 `{"key":"sk-xxx"}`）。
在 Higress 用自定义鉴权 / key-auth 插件把校验指向它（详见《docs/api/模型入口对接指南.md》第 3 节）。
短期联调可先只通转发、Key 强校验随后补。

## 第 6 步：本平台模型路由同步（可选）

管理台「统一网关 → 路由规则」配置后点「同步网关」，将路由推送到 Higress
（需 verify-key/路由同步 API 就绪；当前 sync 为受理占位）。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| Console 打不开 | 看 `docker compose ps` 确认 console 端口映射 |
| 网关 502 | Higress 容器访问宿主模型用了 127.0.0.1 → 改内网 IP；或未 `network connect` |
| 平台内置入口 502 | 确认 api-server 能访问模型地址；`docker compose logs api-server` |
| 模型名不匹配 | 请求 model 必须等于「模型管理」里的模型名称 |
| 401 | Key 无效/禁用/过期；或请求没带 `Authorization: Bearer sk-xxx` |
| 403 | Key 已绑定模型但不含请求的模型（可改为不绑定 = 全部放行） |
| 需要 Key 强校验 | 接 verify-key 端点（第 5 步） |

---

*注：Higress 官方模板/Console 版本迭代快，字段以实际界面为准；本手册给链路要点，避免给可能过时的截图级指引。*
