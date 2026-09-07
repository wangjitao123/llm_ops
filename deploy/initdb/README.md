# initdb 目录说明

本目录挂载到 PostgreSQL 容器的 `/docker-entrypoint-initdb.d`，其中的 `*.sql` / `*.sh`
会在**数据库首次初始化时**自动执行。

## 默认行为

平台业务表由 `api-server` 启动时自动创建（`python -m app.core.init_db` +
`AUTO_CREATE_TABLES=true`），**无需在此放任何建表脚本**即可跑通。

## 可选：请求日志分区表（高吞吐生产建议）

`api_request_log` 默认按普通表创建。日请求量达千万级时，建议改用按月分区：

1. 将 `docs/概要设计/数据库设计/sql/01-create-tables.sql` 中 `api_request_log`
   分区表相关 DDL（含 `PARTITION BY RANGE` 与初始分区、维护函数）复制为
   `01-partition.sql` 放入本目录。
2. 注意：分区 DDL 必须在业务建表**之前**执行（entrypoint 脚本按文件名顺序），
   因此若本目录存在 `01-partition.sql`，`create_all` 会跳过已存在的
   `api_request_log`，两者不冲突。

```bash
# 重建数据卷使 initdb 生效（仅首启需要；已有数据不要删除卷！）
docker compose down -v   # 注意：-v 会删除数据卷，仅限全新环境
docker compose up -d
```
