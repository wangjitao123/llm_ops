# 大模型监测管理平台 — 前端

## 技术栈

- Vue 3 + TypeScript + Vite
- Ant Design Vue 4.x
- Pinia (状态管理)
- Vue Router 4
- ECharts 5 (数据可视化)
- Axios

## 快速开始

```bash
# 安装依赖
pnpm install
# 或
npm install

# 启动开发服务器 (端口 5173)
pnpm dev

# 构建生产版本
pnpm build

# 运行单元测试
pnpm test
```

## 目录结构

```
frontend/
├── src/
│   ├── api/                  # API 请求层
│   │   ├── modelApi.ts       # 模型管理
│   │   ├── keyApi.ts         # Key 管理
│   │   ├── tokenApi.ts       # Token 统计
│   │   ├── gatewayApi.ts     # 网关管理
│   │   ├── finetuneApi.ts    # 模型微调
│   │   ├── compareApi.ts     # 模型对比
│   │   └── systemApi.ts      # 系统管理
│   ├── components/
│   │   └── layout/           # 布局组件
│   ├── composables/          # 组合式函数
│   ├── router/               # 路由配置
│   ├── stores/               # Pinia 状态
│   ├── types/                # TypeScript 类型定义
│   ├── utils/                # 工具函数 (axios 封装等)
│   └── views/                # 页面组件
│       ├── dashboard/        # 总览大屏
│       ├── model/            # 模型管理
│       ├── key/              # Key 管理
│       ├── token/            # Token 统计
│       ├── gateway/          # 统一网关
│       ├── finetune/         # 模型微调
│       ├── compare/          # 模型对比
│       ├── system/           # 系统管理
│       └── login/            # 登录页
├── public/
├── index.html
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| VITE_API_BASE_URL | API 基础路径 | /api |
| VITE_API_TIMEOUT | 请求超时时间 (ms) | 15000 |