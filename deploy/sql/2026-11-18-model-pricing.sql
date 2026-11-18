-- 配额与计费闭环：计费单价表（2026-11-18）
--
-- 什么时候需要手工执行：
--   deploy/.env 里 AUTO_CREATE_TABLES=false 时才需要（关闭了启动自动建表）。
--   默认 true 的部署，api-server 启动时会由 create_all 自动建好，本文件可跳过。
--
-- 执行方式：
--   docker compose exec -T postgres psql -U llmops -d ai_platform \
--     < deploy/sql/2026-11-18-model-pricing.sql
--
-- 说明：
--   本项目没有 Alembic，create_all 只建缺失的表、不会给已有表加列。
--   所以计费单价必须独立成表，不能给 model 表加 price 列。
--   本 DDL 幂等（IF NOT EXISTS），重复执行安全。

CREATE TABLE IF NOT EXISTS model_pricing (
    id                   BIGSERIAL PRIMARY KEY,
    model_id             BIGINT NOT NULL UNIQUE REFERENCES model(id),
    input_price_per_1k   NUMERIC(18, 6) DEFAULT 0,   -- 元 / 千输入 token
    output_price_per_1k  NUMERIC(18, 6) DEFAULT 0,   -- 元 / 千输出 token
    currency             VARCHAR(8) DEFAULT 'CNY',
    remark               VARCHAR(200),
    created_by           VARCHAR(64),
    updated_by           VARCHAR(64),
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_pricing_model_id ON model_pricing (model_id);

-- 校验
SELECT COUNT(*) AS table_ready FROM information_schema.tables
WHERE table_name = 'model_pricing';