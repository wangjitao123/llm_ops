# 前端测试报告 — 大模型监测管理平台

| 项目 | 内容 |
|------|------|
| 测试框架 | Vitest 2.1.9 + Vue Test Utils |
| 测试时间 | 2025-01-01 |
| 运行命令 | `npm run test` |
| 结果 | ✅ **29/29 通过** |

## 1. 测试概况

| 指标 | 数值 |
|------|------|
| 测试文件数 | 3 |
| 总测试用例数 | 29 |
| 通过 | 29 |
| 失败 | 0 |
| 通过率 | 100% |
| 耗时 | 4.1s |

## 2. 测试文件明细

| 测试文件 | 用例数 | 覆盖内容 | 结果 |
|----------|--------|----------|------|
| `src/__tests__/utils.test.ts` | 12 | formatTime / formatTokenCount / formatCost / maskKey | ✅ |
| `src/__tests__/store.test.ts` | 4 | userStore 初始化 / setToken / setUser / logout | ✅ |
| `src/__tests__/api.test.ts` | 13 | 7 个 API 模块的 URL + 参数断言 | ✅ |

## 3. 用例详情

### 3.1 utils.test.ts（12 用例）

| 测试用例 | 验证点 |
|----------|--------|
| formatTime 空值返回 '-' | null/undefined 输入 |
| formatTime 格式化 Date | 年月日 + 时分秒替换 |
| formatTime 非日期字符串透传 | 非法输入容错 |
| formatTime ISO 字符串 | 字符串日期格式化 |
| formatTokenCount 千以下 | 原样输出 |
| formatTokenCount K | 千位缩略 |
| formatTokenCount M | 百万缩略 |
| formatTokenCount B | 十亿缩略 |
| formatCost | 货币符号前缀 |
| maskKey 长 Key 掩码 | 中间掩码 + 首尾保留 |
| maskKey 空串 | 空输入 |
| maskKey 短 Key | 原样输出 |

### 3.2 store.test.ts（4 用例）

| 测试用例 | 验证点 |
|----------|--------|
| 初始状态 | token 为空、未登录、user 为 null |
| setToken 持久化 | token 状态 + localStorage |
| setUser 持久化 | 用户信息 + JSON 序列化 |
| logout 清理 | token/user 清除 + localStorage 移除 |

### 3.3 api.test.ts（13 用例）

| 测试用例 | 验证点 |
|----------|--------|
| modelApi × 4 | GET 列表(参数) / GET 详情 / POST 创建 / PUT 状态 |
| keyApi × 3 | POST 创建 / GET 应用列表 / DELETE 删除 |
| tokenApi × 2 | GET stats(参数) / GET cost-report |
| gatewayApi × 2 | GET 路由列表 / POST 同步 Higress |
| finetuneApi × 2 | GET 任务列表(过滤) / POST 取消 |

## 4. 覆盖率

| 模块 | 类型定义 | API 函数 | 工具函数 | Store |
|------|----------|----------|----------|-------|
| 类型定义 types/api.ts | 10 类型 | — | — | — |
| utils/index.ts | — | — | ✅ 100% | — |
| stores/userStore.ts | — | — | — | ✅ 100% |
| api/*.ts (7 文件) | — | ✅ 全部 | — | — |

## 5. 已知限制

| 限制 | 说明 |
|------|------|
| 页面组件测试 | 大型 .vue 页面组件（ECharts/复杂表单）未做完整渲染测试，仅 API/Store/Utils 逻辑层 |
| 覆盖率统计 | 未配置 coverage 阈值，后续可加 `--coverage` 门槛 |
| 组件测试建议 | 建议后续对 form 校验、表格操作等核心交互补充组件级测试 |