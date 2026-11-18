-- ============================================================
-- 模型压测模块 DDL
-- 数据库: PostgreSQL 16
-- 依赖: model 表已存在
-- ============================================================

-- 1. 压测任务表
CREATE TABLE IF NOT EXISTS perf_task (
    id                  BIGSERIAL PRIMARY KEY,
    name                VARCHAR(128) NOT NULL,
    model_id            BIGINT REFERENCES model(id) ON DELETE SET NULL,
    model_name_snapshot VARCHAR(128),
    status              VARCHAR(16) NOT NULL DEFAULT 'pending',
    mode                VARCHAR(16) NOT NULL,

    -- 压力参数
    parallel            INTEGER,
    number              INTEGER,
    rate                DECIMAL(8,2),
    max_concurrency     INTEGER,
    duration_limit      INTEGER DEFAULT 600,

    -- SLA 参数
    sla_metric          VARCHAR(16),
    sla_threshold_ms    INTEGER,
    sla_lower_bound     INTEGER,
    sla_upper_bound     INTEGER,

    -- 多轮参数
    turns               INTEGER,

    -- 输入构造
    dataset_type        VARCHAR(32) NOT NULL DEFAULT 'random',
    input_length        INTEGER,
    output_length       INTEGER,
    dataset_file        VARCHAR(512),

    -- 高级参数
    stream              BOOLEAN DEFAULT TRUE,
    temperature         DECIMAL(3,2) DEFAULT 0.00,
    request_timeout     INTEGER DEFAULT 60,
    tokenizer_path      VARCHAR(256),

    -- 打法
    target_url          VARCHAR(512) NOT NULL,
    via_gateway         BOOLEAN DEFAULT FALSE,

    -- 参数快照与指纹
    params_json         JSONB,
    fingerprint         VARCHAR(64),

    -- 进度
    progress_sent       INTEGER DEFAULT 0,
    progress_total      INTEGER DEFAULT 0,
    current_rps         DECIMAL(8,2),

    -- 结果摘要
    ttft_mean_ms        DECIMAL(10,2),
    ttft_p99_ms         DECIMAL(10,2),
    tpot_mean_ms        DECIMAL(10,2),
    output_throughput   DECIMAL(12,2),
    request_throughput  DECIMAL(10,2),
    success_rate        DECIMAL(5,2),
    success_count       INTEGER,
    result_json         JSONB,

    -- 时间与错误
    error_message       TEXT,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    duration_seconds    INTEGER,

    created_by          VARCHAR(64) NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMP,

    CONSTRAINT ck_perf_task_status CHECK (
        status IN ('pending', 'running', 'completed', 'failed', 'cancelled')
    ),
    CONSTRAINT ck_perf_task_mode CHECK (
        mode IN ('closed_loop', 'open_loop', 'sla', 'multi_turn')
    )
);

CREATE INDEX IF NOT EXISTS idx_perf_task_status_time
    ON perf_task (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_perf_task_model
    ON perf_task (model_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_perf_task_fingerprint
    ON perf_task (fingerprint);
CREATE INDEX IF NOT EXISTS idx_perf_task_created_by
    ON perf_task (created_by);

-- 2. 压测日志表
CREATE TABLE IF NOT EXISTS perf_task_log (
    id          BIGSERIAL PRIMARY KEY,
    task_id     BIGINT NOT NULL REFERENCES perf_task(id) ON DELETE CASCADE,
    level       VARCHAR(8) NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_perf_log_task_time
    ON perf_task_log (task_id, created_at DESC);
