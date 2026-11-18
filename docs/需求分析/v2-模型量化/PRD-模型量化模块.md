# PRD - 模型量化模块

## 文档信息

| 项目 | 内容 |
|------|------|
| 产品名称 | 大模型监测管理平台 |
| 模块名称 | 模型量化（M08） |
| 版本号 | v1.0 |
| 原型版本 | v3（已确认） |
| 原型路径 | `docs/需求分析/prototype-v3/模型量化-原型.html` |

## 1. 产品定位

### 1.1 产品背景

当前平台已具备模型管理、Key管理、Token统计、统一网关、模型微调、模型对比评估等功能。模型量化是平台能力的重要补充，让用户能够在平台内完成「选模型→配参数→GPU执行→结果注册」的全流程量化管理。

### 1.2 目标用户

| 角色 | 典型用户 | 核心诉求 |
|------|---------|---------|
| 平台管理员 | 运维/算法工程师 | 通过平台便捷地将开源模型量化为低精度格式，降低部署成本 |
| GPU Worker（系统） | 自动执行 | 自动从队列获取任务，执行量化并注册结果 |

### 1.3 产品目标

1. 提供统一的量化任务管理界面
2. 支持 GPTQ / AWQ / bitsandbytes 三种主流量化算法
3. 量化完成后自动注册为平台可用模型
4. 支持自定义校准数据集
5. 提供任务运行日志和进度追踪

## 2. 功能清单

| 编号 | 功能名称 | 优先级 | 复杂度 | 来源页面 |
|------|---------|--------|--------|---------|
| FQ-01 | 量化任务列表查看 | Must | S | 主页面 |
| FQ-02 | 按状态筛选任务 | Must | S | 主页面 |
| FQ-03 | 创建量化任务 | Must | M | 创建弹窗 |
| FQ-04 | 快速参数模板 | Should | S | 创建弹窗·模板栏 |
| FQ-05 | 校准数据集选择 | Must | M | 创建弹窗·校准数据区 |
| FQ-06 | 提交量化任务 | Must | S | 操作按钮 |
| FQ-07 | 取消进行中的任务 | Should | S | 操作按钮 |
| FQ-08 | 重试失败任务 | Should | S | 操作按钮 |
| FQ-09 | 删除已完成/失败/已取消任务 | Should | S | 操作按钮 |
| FQ-10 | 查看任务详情 | Must | S | 详情弹窗 |
| FQ-11 | 任务运行日志查看 | Must | M | 详情弹窗·日志面板 |
| FQ-12 | 下载量化模型 | Could | M | 操作按钮 |
| FQ-13 | 量化完成后自动注册模型 | Must | H | 后端逻辑 |
| FQ-14 | 模型详情←→量化任务双向追溯 | Should | M | 详情弹窗 + 模型详情页 |
| FQ-15 | 自定义校准文件上传 | Could | S | 创建弹窗·文件上传 |

## 3. 页面结构

### 3.1 侧边导航
- 菜单项：模型量化（💡 图标，位于「模型对比」和「系统管理」之间）
- 标签：`NEW` 红色徽章

### 3.2 主页面（量化任务列表）
| 区域 | 内容 | 说明 |
|------|------|------|
| 信息横幅 | 💡 平台集成了 GPTQ/AWQ/bnb 三种算法... | 蓝色渐变背景 |
| 筛选区 | 状态下拉框 + 查询按钮 | 支持按全部/待提交/排队中/运行中/已完成/失败筛选 |
| 创建按钮 | 「＋ 创建量化任务」蓝色按钮 | 打开创建弹窗 |
| 任务表格 | 名称(含量化方案标签)/状态(点+文字)/进度条/结果模型链接/操作 | 行操作：详情、提交执行/取消/重试/删除 |

### 3.3 创建弹窗
| 区域 | 内容 |
|------|------|
| 快速模板 | W4A16-GPTQ(推荐) / W4A16-AWQ / W4A16-bnb / W8A16-GPTQ(无损) / W3A16-AWQ 极限压缩 |
| 基本信息 | 任务名称 *、HF 模型 ID *、输出模型名称（选填） |
| 量化配置 | 量化算法 *（GPTQ/AWQ/bnb）、权重精度 *（2/3/4/8 bit）、分组大小 *（32/64/128/256） |
| 校准数据 | 样本数（默认 256）、数据来源（默认 wikitext-2 / 自定义校准文本 / 上传 .txt 文件） |
| 高级设置（折叠） | 输出路径（默认 /models/） |

### 3.4 详情弹窗
| 区域 | 内容 |
|------|------|
| 参数表格 | 任务名称、基座模型、量化方案、精度、分组大小、校准数据、输出路径、结果模型(可点击跳转)、错误信息、创建人、创建时间 |
| 运行日志 | 深色终端风格日志面板，按状态显示不同内容 |

## 4. 业务流程

```
用户 → 打开模型量化页面
     → 点击「创建量化任务」
     → 填写配置（或使用快速模板）
     → 选择校准数据（默认/自定义/上传）
     → 创建并提交
         ↓
     GPU Worker 接收任务 (RabbitMQ 队列: quantization)
         ↓
     1. 从 HuggingFace 下载模型
     2. 加载校准数据
     3. 执行量化（GPTQ/AWQ/bnb）
     4. 保存到共享卷 /models/
     5. 自动注册到平台 model 表
     6. 更新任务状态 + 结果模型ID
         ↓
     用户查看进度 → 查看日志 → 在模型管理中看到量化后模型
```

## 5. 数据模型

### 5.1 quantization_task 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 主键 |
| name | VARCHAR(100) NOT NULL | 任务名称 |
| base_model_id | BIGINT FK→model.id | 关联的平台模型ID（可选） |
| hf_model_id | VARCHAR(300) NOT NULL | HuggingFace 模型 ID |
| output_name | VARCHAR(100) | 量化后模型命名（可选） |
| algorithm | VARCHAR(20) NOT NULL DEFAULT 'gptq' | GPTQ / AWQ / bitsandbytes |
| weight_bits | SMALLINT DEFAULT 4 | 2/3/4/8 |
| activation_bits | SMALLINT DEFAULT 16 | 固定 16 |
| group_size | INT DEFAULT 128 | 32/64/128/256 |
| calib_samples | INT DEFAULT 256 | 校准样本数 |
| calib_source | VARCHAR(20) DEFAULT 'default' | default / custom |
| calib_text | TEXT | 自定义校准文本（仅 calib_source=custom 时）|
| output_path | VARCHAR(500) | 量化模型保存路径 |
| status | VARCHAR(20) DEFAULT 'pending' | pending/queued/running/completed/failed/cancelled |
| progress | INT DEFAULT 0 | 0-100 |
| error_message | TEXT | 错误信息 |
| result_model_id | BIGINT FK→model.id | 结果模型ID |
| created_by | VARCHAR(64) NOT NULL | 创建人 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

## 6. 业务规则

| # | 规则 | 说明 |
|---|------|------|
| BR-01 | 任务提交 | pending 状态可提交为 queued；running/queued 可取消；其他状态不可操作 |
| BR-02 | 自动注册 | 量化完成后自动创建 Model 记录，provider='quantized'，version 含精度信息 |
| BR-03 | 并发限制 | GPU Worker 单次只处理一个任务（concurrency=1），避免显存资源争抢 |
| BR-04 | 超时限制 | 单任务超时上限 3 小时（Celery time_limit=10800） |
| BR-05 | 校准数据 | 默认使用 wikitext-2 数据集；自定义文本按行分割，每条作为独立样本 |
| BR-06 | 输出路径 | 自动生成路径：`/models/{safe_name}-{algo}-w{wBits}a{aBits}` |
| BR-07 | 模型命名 | 量化后 Model name = `{output_name || task_name} ({algorithm})`，version = `1.0-q{wBits}a{aBits}-{algorithm}` |
| BR-08 | 幂等重试 | 失败任务点重试 = 状态重置为 queued，清空 error_message |

## 7. 非功能需求

| 需求 | 指标 |
|------|------|
| GPU Worker 镜像大小 | ≤10GB（含 PyTorch + CUDA + quantization libs）|
| 7B 模型量化耗时 | ≤30 分钟（GPTQ W4A16）|
| 70B 模型量化耗时 | ≤3 小时 |
| 任务状态更新延迟 | ≤5 秒 |
| 日志实时性 | 近实时（Celery task 内 print 输出） |

## 8. 边界条件

| 场景 | 处理方式 |
|------|---------|
| HF 模型 ID 不存在 | GPU Worker 捕获 HTTPException，标记任务为 failed |
| GPU 显存不足 | Worker 捕获 CUDA OOM，标记为 failed + 保留错误信息 |
| 网络下载中断 | Worker 重试 2 次，仍失败则标记 failed |
| 校准数据集为空 | 使用默认 wikitext-2 降级 |
| 多任务排队 | RabbitMQ 队列保证 FIFO，worker concurrency=1 串行处理 |
| 任务中途取消 | Worker 进程内捕获 SIGTERM，标记为 cancelled |

## 9. REQ-ID 追溯矩阵

| REQ-ID | 功能描述 | MoSCoW | 原型参考 | 状态 |
|--------|---------|--------|---------|------|
| REQ-QUANT-001 | 量化任务列表 | Must | 原型 v3 主页表格 | 待实现 |
| REQ-QUANT-002 | 创建量化任务（含模板+校准）| Must | 原型 v3 创建弹窗 | 待实现 |
| REQ-QUANT-003 | 任务状态管理（提交/取消/重试/删除）| Should | 原型 v3 操作按钮 | 待实现 |
| REQ-QUANT-004 | 任务详情查看（含日志）| Must | 原型 v3 详情弹窗 | 待实现 |
| REQ-QUANT-005 | GPU Worker 量化执行 | Must | 后端 | 待实现 |
| REQ-QUANT-006 | 量化结果自动注册模型 | Must | 后端 | 待实现 |
| REQ-QUANT-007 | 模型←→任务双向追溯 | Should | 原型 v3 详情弹窗 | 待实现 |
| REQ-QUANT-008 | 模型文件下载 | Could | 原型 v3 操作按钮 | 待实现 |