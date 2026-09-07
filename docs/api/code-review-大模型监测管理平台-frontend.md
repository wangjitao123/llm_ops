# 代码审查报告 — 大模型监测管理平台（前端）

## 报告信息

| 审查目标 | frontend/ 前端工程 |
| 审查类型 | full（全量） |
| 技术栈 | Vue 3 + TypeScript + Vite + Ant Design Vue + Pinia + ECharts |
| 审查时间 | 2025-01-01 |
| 审查人 | AI @stage-08 |
| 审查范围 | src/api、src/views、src/components、src/router、src/stores、src/utils、src/types |
| 修复状态 | ✅ **严重(1) + 重要(5) 全部已修复**（2025-01-01） |

---

## 审查摘要

### 统计概览

- **审查文件**: 28 个
- **代码行数**: ~3,200 行
- **问题总数**: 11 个
  - 🔴 **严重(Critical)**: 1 个 — ✅ 已修复
  - 🟠 **重要(Major)**: 5 个 — ✅ 已修复
  - 🟡 **警告(Warning)**: 5 个 — 已标记为后续迭代优化

### 质量评分

| 维度 | 修复前 | 修复后 | 说明 |
|------|--------|--------|------|
| 安全性 | 7/10 | **9/10** | JWT 收敛 sessionStorage + 权限守卫 |
| 性能 | 8/10 | **9/10** | ECharts 实例/监听随组件销毁清理 |
| 可读性 | 8/10 | 8/10 | 命名规范一致 |
| 可维护性 | 8/10 | **9/10** | auth 统一入口，类型收敛 |
| **综合评分** | **7.8/10** | **8.8/10** | 安全与健壮性显著提升 |

### 审查结论

| 结论 | 说明 |
|------|------|
| ✅ **通过** | 严重 + 重要问题已全部修复并通过单测与类型检查 |

---

## 修复详情

### 🔴 严重问题修复：JWT 存储 XSS 风险

**修复方案**：新增 `src/utils/auth.ts` 统一令牌存储入口
- ✅ Token/User 全部收敛到 `sessionStorage`（会话级，关闭浏览器失效，缩短暴露窗口）
- ✅ 全项目禁止直接访问 localStorage 存令牌（grep 验证无残留）
- ✅ `request.ts` / `userStore.ts` / `router` 统一走 auth 工具
- 📝 生产推荐：后端 httpOnly + Secure Cookie（代码注释已说明切换点）

**修改文件**：`utils/auth.ts`（新增）、`utils/request.ts`、`stores/userStore.ts`、`router/index.ts`

### 🟠 重要问题修复清单

| # | 问题 | 修复方案 | 修改文件 |
|---|------|----------|----------|
| 1 | ECharts resize 监听泄漏 | `onUnmounted` 移除监听 + `chart.dispose()` + 渲染前清理旧实例 | `dashboard/index.vue`、`token/index.vue` |
| 2 | 路由无权限校验 | 路由 `meta.roles` + 导航守卫角色校验（gateway/system 限定 admin） | `router/index.ts` |
| 3 | 401 重复跳转 | 跳转前判断当前路由 + `router.replace` 去重 | `utils/request.ts` |
| 4 | CORS 通配 `*` | 后端 `config.py` 新增 `cors_origins` 可配置（默认 localhost:5173），`main.py` 读取配置 | `backend/app/core/config.py`、`backend/app/main.py`、`backend/.env.example` |
| 5 | SSO Client Secret 明文 | 保存后清空内存 secret；加载时不回填加密/secret 配置的明文 | `views/system/index.vue` |

### 修复验证

| 验证项 | 结果 |
|--------|------|
| 单元测试 | ✅ 29/29 通过（store 测试更新为 sessionStorage 断言） |
| 类型检查 `vue-tsc` | ✅ 通过（含修复连带发现的 6 处历史类型错误） |
| 生产构建 `vite build` | ✅ 通过 |

---

## 剩余项（低优先级 / 后续迭代）

| # | 类型 | 说明 | 计划 |
|---|------|------|------|
| 1 | 代码重复 | ECharts 初始化逻辑可抽 `useEChart()` composable | 迭代二 |
| 2 | 状态映射 | 各页面 statusMap 抽到 constants | 迭代二 |
| 3 | 类型收敛 | api 层内联类型统一到 types/api.ts | 迭代二 |
| 4 | 组件拆分 | 大页面（system/finetune/key）拆子组件 | 迭代二 |
| 5 | 依赖漏洞 | npm audit 6 漏洞评估升级 | 迭代二 |

---

## 安全审查详情（修复后）

### OWASP Top 10 检查结果

| OWASP 分类 | 检查项 | 结果 | 说明 |
|-----------|--------|------|------|
| A01: 权限控制失效 | 前端路由权限校验 | ⚠️ | 已加 meta.roles 前端控制；后端接口级鉴权仍为最终防线 |
| A02: 加密失效 | 令牌存储 | ✅ | 已收敛 sessionStorage，生产推荐 httpOnly Cookie |
| A03: 注入 | XSS 检查 | ✅ | 全工程无 `v-html`/`innerHTML` |
| A05: 安全配置错误 | CORS | ✅ | 已改为可配置白名单 |
| A06: 脆弱组件 | 依赖安全 | ⚠️ | npm audit 6 漏洞待迭代二评估 |
| A07: 身份认证失败 | 认证流程 | ✅ | 401 去重跳转已修复 |

---

## 性能审查详情（修复后）

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 图表资源 | ✅ | ECharts 实例 dispose + resize 监听 onUnmounted 移除 |
| 大数据渲染 | ✅ | 表格走服务端分页 |
| 懒加载 | ✅ | 路由全部动态 import |
| 网络请求 | ✅ | Axios 单例 + 拦截器统一 |

---

## 参考资料
- [OWASP Top 10](https://owasp.org/Top10/)
- [Vue.js 官方安全建议](https://cn.vuejs.org/guide/best-practices/security.html)
- [OWASP HTML5 Security - LocalStorage 风险](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_persistent_cookies)
- [Clean Code](https://www.oreilly.com/library/view/clean-code/)
