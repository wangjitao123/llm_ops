-- ============================================================
-- 模型部署模块 DDL
-- 数据库: PostgreSQL 15+
-- ============================================================

-- 1. 部署配置表
CREATE TABLE IF NOT EXISTS deployment (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    deploy_type     VARCHAR(16) NOT NULL DEFAULT 'managed',
    status          VARCHAR(16) NOT NULL DEFAULT 'deploying',
    base_model_id   INT REFERENCES model(id) ON DELETE SET NULL,
    hf_model_id     VARCHAR(256),
    endpoint_url    VARCHAR(512) NOT NULL,
    engine          VARCHAR(16),
    gpu_ids         INTEGER[],
    gpu_count       INT DEFAULT 1,
    gpu_memory_gb   DECIMAL(6,2),
    max_concurrency INT DEFAULT 32,
    max_input_tokens INT DEFAULT 4096,
    system_prompt   TEXT,
    temperature     DECIMAL(3,2) DEFAULT 0.70,
    top_p           DECIMAL(3,2) DEFAULT 0.90,
    max_tokens      INT DEFAULT 4096,
    frequency_penalty DECIMAL(3,2) DEFAULT 0.00,
    tools_json      JSONB,
    web_search_enabled BOOLEAN DEFAULT FALSE,
    web_search_config JSONB,
    env_vars        JSONB,
    auto_register   BOOLEAN DEFAULT TRUE,
    health_check_enabled BOOLEAN DEFAULT TRUE,
    error_message   TEXT,
    created_by      VARCHAR(64) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_deployment_name UNIQUE (name),
    CONSTRAINT ck_deployment_deploy_type CHECK (deploy_type IN ('managed', 'conda', 'docker', 'other')),
    CONSTRAINT ck_deployment_status CHECK (status IN ('deploying', 'running', 'stopped', 'failed', 'deleted'))
);

CREATE INDEX idx_deployment_status ON deployment(status);
CREATE INDEX idx_deployment_deploy_type ON deployment(deploy_type);
CREATE INDEX idx_deployment_base_model ON deployment(base_model_id);
CREATE INDEX idx_deployment_created_at ON deployment(created_at DESC);

-- 2. 健康检查日志表
CREATE TABLE IF NOT EXISTS deployment_health_log (
    id              BIGSERIAL PRIMARY KEY,
    deployment_id   BIGINT NOT NULL REFERENCES deployment(id) ON DELETE CASCADE,
    status_code     INT,
    latency_ms      INT,
    is_healthy      BOOLEAN NOT NULL,
    error_message   TEXT,
    checked_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_health_deploy_time ON deployment_health_log(deployment_id, checked_at DESC);
CREATE INDEX idx_health_checked_at ON deployment_health_log(checked_at);

-- 3. 性能指标聚合表
CREATE TABLE IF NOT EXISTS deployment_metrics (
    id              BIGSERIAL PRIMARY KEY,
    deployment_id   BIGINT NOT NULL REFERENCES deployment(id) ON DELETE CASCADE,
    qps             DECIMAL(8,2),
    p50_latency_ms  DECIMAL(8,2),
    p99_latency_ms  DECIMAL(8,2),
    avg_latency_ms  DECIMAL(8,2),
    error_rate      DECIMAL(5,4),
    total_requests  INT DEFAULT 0,
    window_start    TIMESTAMP NOT NULL,
    window_end      TIMESTAMP NOT NULL
);

CREATE INDEX idx_metrics_deploy_window ON deployment_metrics(deployment_id, window_start DESC);

-- 4. 部署日志表
CREATE TABLE IF NOT EXISTS deployment_log (
    id              BIGSERIAL PRIMARY KEY,
    deployment_id   BIGINT NOT NULL REFERENCES deployment(id) ON DELETE CASCADE,
    level           VARCHAR(8) NOT NULL DEFAULT 'info',
    message         TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_log_deploy_time ON deployment_log(deployment_id, created_at DESC);