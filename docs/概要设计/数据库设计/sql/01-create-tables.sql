-- ============================================================
-- 大模型监测管理平台 DDL 建表脚本
-- 数据库: PostgreSQL 16
-- 创建日期: 2025-01-01
-- ============================================================

-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 模型管理模块
-- ============================================================

-- 模型表
CREATE TABLE model (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    api_base_url VARCHAR(500) NOT NULL,
    api_key_encrypted VARCHAR(500) NOT NULL,
    qps_limit INT NOT NULL DEFAULT 100,
    timeout_ms INT NOT NULL DEFAULT 60000,
    weight INT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    health_check_url VARCHAR(500),
    model_config JSONB,
    description TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_model_provider ON model(provider) WHERE deleted_at IS NULL;
CREATE INDEX idx_model_status ON model(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_model_name ON model(name) WHERE deleted_at IS NULL;
COMMENT ON TABLE model IS '模型表 - 存储接入的大模型配置信息';
COMMENT ON COLUMN model.status IS '状态: online/offline/high_latency/pending';
COMMENT ON COLUMN model.provider IS '提供商: deepseek/openai/aliyun/baidu';

-- 模型版本表
CREATE TABLE model_version (
    id BIGSERIAL PRIMARY KEY,
    model_id BIGINT NOT NULL REFERENCES model(id),
    version VARCHAR(50) NOT NULL,
    model_config_snapshot JSONB,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    change_log TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_mv_model_id ON model_version(model_id) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uk_mv_model_version ON model_version(model_id, version) WHERE deleted_at IS NULL;
COMMENT ON TABLE model_version IS '模型版本表 - 记录模型配置变更历史';
COMMENT ON COLUMN model_version.is_current IS '是否当前生效版本';

-- 模型心跳表
CREATE TABLE model_heartbeat (
    id BIGSERIAL PRIMARY KEY,
    model_id BIGINT NOT NULL REFERENCES model(id),
    status VARCHAR(20) NOT NULL,
    response_time_ms INT,
    error_message TEXT,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_mh_model_id ON model_heartbeat(model_id);
CREATE INDEX idx_mh_checked_at ON model_heartbeat(checked_at);
COMMENT ON TABLE model_heartbeat IS '模型心跳表 - 记录模型健康检查结果';
COMMENT ON COLUMN model_heartbeat.status IS '状态: online/offline/high_latency';

-- ============================================================
-- Key 管理模块
-- ============================================================

-- 应用表
CREATE TABLE application (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uk_application_name ON application(name) WHERE deleted_at IS NULL;
COMMENT ON TABLE application IS '应用表 - 接入 AI 网关的业务应用';

-- API Key 表
CREATE TABLE app_key (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    key_prefix VARCHAR(10) NOT NULL,
    application_id BIGINT REFERENCES application(id),
    created_by VARCHAR(64) NOT NULL,
    qps_limit INT,
    rpm_limit INT,
    rpd_limit INT,
    token_quota BIGINT,
    token_used BIGINT NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_app_key_status ON app_key(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_app_key_application_id ON app_key(application_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_app_key_expires_at ON app_key(expires_at) WHERE deleted_at IS NULL AND status = 'active';
COMMENT ON TABLE app_key IS 'API Key 表 - 存储 API Key 信息';
COMMENT ON COLUMN app_key.key_hash IS 'Key 的 SHA-256 哈希值';
COMMENT ON COLUMN app_key.key_prefix IS 'Key 前缀（用于显示，如 sk-8a3f）';
COMMENT ON COLUMN app_key.status IS '状态: active/disabled/expired/revoked';

-- Key-模型权限关联表
CREATE TABLE app_key_model (
    id BIGSERIAL PRIMARY KEY,
    app_key_id BIGINT NOT NULL REFERENCES app_key(id),
    model_id BIGINT NOT NULL REFERENCES model(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uk_akm_key_model ON app_key_model(app_key_id, model_id);
CREATE INDEX idx_akm_model_id ON app_key_model(model_id);
COMMENT ON TABLE app_key_model IS 'Key-模型权限关联表 - 控制 Key 可访问的模型';

-- 全局限流配置表
CREATE TABLE rate_limit_config (
    id BIGSERIAL PRIMARY KEY,
    config_key VARCHAR(50) NOT NULL UNIQUE,
    global_qps INT NOT NULL DEFAULT 5000,
    default_key_qps INT NOT NULL DEFAULT 100,
    default_key_rpm INT NOT NULL DEFAULT 6000,
    default_key_rpd INT NOT NULL DEFAULT 100000,
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE rate_limit_config IS '全局限流配置表 - 默认速率限制参数';

-- ============================================================
-- 网关模块
-- ============================================================

-- 路由规则表
CREATE TABLE route_rule (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    path_pattern VARCHAR(200) NOT NULL,
    match_type VARCHAR(20) NOT NULL DEFAULT 'exact',
    strategy VARCHAR(20) NOT NULL DEFAULT 'weighted',
    status VARCHAR(20) NOT NULL DEFAULT 'disabled',
    priority INT NOT NULL DEFAULT 0,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_rr_status ON route_rule(status) WHERE deleted_at IS NULL;
COMMENT ON TABLE route_rule IS '路由规则表 - 定义 API 请求的路由分发规则';
COMMENT ON COLUMN route_rule.match_type IS '匹配方式: exact/prefix/regex';
COMMENT ON COLUMN route_rule.strategy IS '策略: weighted/active_standby/single';
COMMENT ON COLUMN route_rule.status IS '状态: enabled/disabled';

-- 路由-模型关联表
CREATE TABLE route_rule_model (
    id BIGSERIAL PRIMARY KEY,
    route_rule_id BIGINT NOT NULL REFERENCES route_rule(id),
    model_id BIGINT NOT NULL REFERENCES model(id),
    priority INT NOT NULL DEFAULT 0,
    weight INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uk_rrm_route_model ON route_rule_model(route_rule_id, model_id);
COMMENT ON TABLE route_rule_model IS '路由-模型关联表 - 定义路由规则指向的模型及权重';

-- API 请求日志表（分区表）
CREATE TABLE api_request_log (
    id BIGSERIAL,
    request_id VARCHAR(64) NOT NULL,
    app_key_id BIGINT,
    model_id BIGINT,
    route_rule_id BIGINT,
    request_path VARCHAR(200) NOT NULL,
    request_method VARCHAR(10) NOT NULL DEFAULT 'POST',
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    response_time_ms INT NOT NULL DEFAULT 0,
    status_code INT NOT NULL DEFAULT 200,
    client_ip VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_arl_created_at ON api_request_log(created_at);
CREATE INDEX idx_arl_app_key_id ON api_request_log(app_key_id);
CREATE INDEX idx_arl_model_id ON api_request_log(model_id);
CREATE INDEX idx_arl_request_id ON api_request_log(request_id);
COMMENT ON TABLE api_request_log IS 'API 请求日志表（分区表） - 记录所有网关请求明细';

-- 创建初始分区（每月一个）
CREATE TABLE api_request_log_2025_01 PARTITION OF api_request_log
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE api_request_log_2025_02 PARTITION OF api_request_log
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
CREATE TABLE api_request_log_2025_03 PARTITION OF api_request_log
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');
CREATE TABLE api_request_log_2025_04 PARTITION OF api_request_log
    FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');
CREATE TABLE api_request_log_2025_05 PARTITION OF api_request_log
    FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');
CREATE TABLE api_request_log_2025_06 PARTITION OF api_request_log
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');

-- ============================================================
-- Token 统计模块
-- ============================================================

-- Token 统计数据-小时聚合表
CREATE TABLE token_stats_hourly (
    id BIGSERIAL PRIMARY KEY,
    stats_date DATE NOT NULL,
    stats_hour SMALLINT NOT NULL,
    dimension_type VARCHAR(20) NOT NULL,
    dimension_id BIGINT NOT NULL,
    request_count INT NOT NULL DEFAULT 0,
    prompt_tokens BIGINT NOT NULL DEFAULT 0,
    completion_tokens BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    total_cost DECIMAL(18,6) NOT NULL DEFAULT 0,
    avg_response_ms INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tsh_dim ON token_stats_hourly(dimension_type, dimension_id, stats_date);
CREATE INDEX idx_tsh_date ON token_stats_hourly(stats_date);
COMMENT ON TABLE token_stats_hourly IS 'Token 统计小时表 - 按小时聚合的 Token 用量数据';
COMMENT ON COLUMN token_stats_hourly.dimension_type IS '维度类型: model/application/key';

-- Token 统计数据-天聚合表
CREATE TABLE token_stats_daily (
    id BIGSERIAL PRIMARY KEY,
    stats_date DATE NOT NULL,
    dimension_type VARCHAR(20) NOT NULL,
    dimension_id BIGINT NOT NULL,
    request_count INT NOT NULL DEFAULT 0,
    prompt_tokens BIGINT NOT NULL DEFAULT 0,
    completion_tokens BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    total_cost DECIMAL(18,6) NOT NULL DEFAULT 0,
    avg_response_ms INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tsd_dim ON token_stats_daily(dimension_type, dimension_id, stats_date);
CREATE INDEX idx_tsd_date ON token_stats_daily(stats_date);
COMMENT ON TABLE token_stats_daily IS 'Token 统计天表 - 按天聚合的 Token 用量数据';

-- ============================================================
-- 微调模块
-- ============================================================

-- 数据集表
CREATE TABLE dataset (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    format VARCHAR(20) NOT NULL,
    sample_count INT NOT NULL DEFAULT 0,
    file_size BIGINT NOT NULL DEFAULT 0,
    file_path VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64),
    version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    annotation_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    description TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_ds_created_by ON dataset(created_by) WHERE deleted_at IS NULL;
CREATE INDEX idx_ds_annotation_status ON dataset(annotation_status) WHERE deleted_at IS NULL;
COMMENT ON TABLE dataset IS '数据集表 - 存储微调用数据集信息';
COMMENT ON COLUMN dataset.format IS '格式: jsonl/csv/json/parquet';
COMMENT ON COLUMN dataset.annotation_status IS '标注状态: pending/labeling/labeled/reviewing/reviewed';

-- 微调任务表
CREATE TABLE finetune_task (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    base_model_id BIGINT NOT NULL REFERENCES model(id),
    dataset_id BIGINT NOT NULL REFERENCES dataset(id),
    val_dataset_id BIGINT REFERENCES dataset(id),
    hyper_params JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    progress SMALLINT NOT NULL DEFAULT 0,
    loss_value DECIMAL(10,6),
    output_model_version_id BIGINT REFERENCES model_version(id),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_ft_status ON finetune_task(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_ft_created_by ON finetune_task(created_by) WHERE deleted_at IS NULL;
CREATE INDEX idx_ft_base_model_id ON finetune_task(base_model_id) WHERE deleted_at IS NULL;
COMMENT ON TABLE finetune_task IS '微调任务表 - 管理模型微调任务的完整生命周期';
COMMENT ON COLUMN finetune_task.status IS '状态: pending/queued/running/paused/completed/failed/cancelled/deployed';

-- 微调评估表
CREATE TABLE finetune_eval (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES finetune_task(id),
    accuracy_before DECIMAL(5,2),
    accuracy_after DECIMAL(5,2),
    bleu_before DECIMAL(5,4),
    bleu_after DECIMAL(5,4),
    rouge_l_before DECIMAL(5,4),
    rouge_l_after DECIMAL(5,4),
    latency_before_ms INT,
    latency_after_ms INT,
    eval_report JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uk_fe_task_id ON finetune_eval(task_id);
COMMENT ON TABLE finetune_eval IS '微调评估表 - 记录微调前后的模型性能指标对比';

-- ============================================================
-- 模型对比评估模块
-- ============================================================

-- 模型对比评估表
CREATE TABLE model_eval (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    model_ids JSONB NOT NULL,
    dimension_weights JSONB NOT NULL DEFAULT '{"quality": 30, "latency": 15, "cost": 15, "context": 10, "stability": 10, "throughput": 10, "ease_of_use": 10}',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    result JSONB,
    recommendation TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

COMMENT ON TABLE model_eval IS '模型对比评估表 - 记录多模型多维度对比评估结果';

-- ============================================================
-- 系统管理模块
-- ============================================================

-- 预警规则表
CREATE TABLE alert_rule (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    metric_type VARCHAR(20) NOT NULL,
    threshold_value BIGINT NOT NULL,
    threshold_mode VARCHAR(10) NOT NULL DEFAULT 'fixed',
    warn_at_percent SMALLINT NOT NULL DEFAULT 80,
    notify_channels JSONB NOT NULL DEFAULT '["dingtalk"]',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_ar_enabled ON alert_rule(enabled) WHERE deleted_at IS NULL;
COMMENT ON TABLE alert_rule IS '预警规则表 - 配置 Token 用量预警规则';
COMMENT ON COLUMN alert_rule.metric_type IS '指标类型: daily_token/monthly_token/daily_cost/monthly_cost';
COMMENT ON COLUMN alert_rule.threshold_mode IS '模式: fixed/percentage';

-- 告警日志表
CREATE TABLE alert_log (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NOT NULL REFERENCES alert_rule(id),
    alert_level VARCHAR(10) NOT NULL,
    current_value BIGINT NOT NULL,
    threshold_value BIGINT NOT NULL,
    message TEXT NOT NULL,
    notified BOOLEAN NOT NULL DEFAULT FALSE,
    notified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_al_rule_id ON alert_log(rule_id);
CREATE INDEX idx_al_level ON alert_log(alert_level);
CREATE INDEX idx_al_created_at ON alert_log(created_at);
COMMENT ON TABLE alert_log IS '告警日志表 - 记录预警触发历史和通知状态';

-- 通知配置表
CREATE TABLE notification_config (
    id BIGSERIAL PRIMARY KEY,
    channel VARCHAR(20) NOT NULL,
    config JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uk_nc_channel ON notification_config(channel);
COMMENT ON TABLE notification_config IS '通知配置表 - 存储钉钉等通知渠道的配置信息';

-- 操作审计日志表
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    action_detail TEXT NOT NULL,
    target_type VARCHAR(50),
    target_id BIGINT,
    client_ip VARCHAR(50),
    result VARCHAR(10) NOT NULL DEFAULT 'success',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_al_user_id ON audit_log(user_id);
CREATE INDEX idx_al_action_type ON audit_log(action_type);
CREATE INDEX idx_al_created_at ON audit_log(created_at);
CREATE INDEX idx_al_target ON audit_log(target_type, target_id);
COMMENT ON TABLE audit_log IS '操作审计日志表 - 记录用户关键操作，用于安全审计';
COMMENT ON COLUMN audit_log.result IS '结果: success/failure';

-- ============================================================
-- 系统配置表（修复 F-018 SSO 配置缺失）
-- ============================================================
CREATE TABLE system_config (
    id BIGSERIAL PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    config_group VARCHAR(50) NOT NULL DEFAULT 'sso',
    description VARCHAR(500),
    encrypted BOOLEAN NOT NULL DEFAULT FALSE,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sc_config_group ON system_config(config_group);
COMMENT ON TABLE system_config IS '系统配置表 - 存储 SSO、钉钉等系统配置';
COMMENT ON COLUMN system_config.config_group IS '分组: sso/notification/general';

-- 数据集版本表（修复 F-015.4 数据集版本管理）
CREATE TABLE dataset_version (
    id BIGSERIAL PRIMARY KEY,
    dataset_id BIGINT NOT NULL REFERENCES dataset(id),
    version VARCHAR(20) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64),
    sample_count INT NOT NULL DEFAULT 0,
    file_size BIGINT NOT NULL DEFAULT 0,
    change_log TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uk_dv_dataset_version ON dataset_version(dataset_id, version);
CREATE INDEX idx_dv_dataset_id ON dataset_version(dataset_id);
COMMENT ON TABLE dataset_version IS '数据集版本表 - 数据集的版本历史记录';

-- 模型对比评估表（修复 F-017 模型对比评估）
CREATE TABLE model_eval (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    model_ids JSONB NOT NULL,
    dimension_weights JSONB NOT NULL DEFAULT '{"quality":30,"latency":15,"cost":15,"context":10,"stability":10,"throughput":10,"ease_of_use":10}',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    result JSONB,
    recommendation TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

COMMENT ON TABLE model_eval IS '模型对比评估表 - 多模型多维度对比评估';

-- 导出任务表（修复 F-009 费用报表导出）
CREATE TABLE export_task (
    id BIGSERIAL PRIMARY KEY,
    task_type VARCHAR(20) NOT NULL,
    params JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    file_path VARCHAR(500),
    file_format VARCHAR(10) NOT NULL DEFAULT 'csv',
    file_size BIGINT,
    expires_at TIMESTAMPTZ,
    error_message TEXT,
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_et_created_by ON export_task(created_by);
CREATE INDEX idx_et_status ON export_task(status);
COMMENT ON TABLE export_task IS '导出任务表 - 记录异步导出任务（报表/日志）';
COMMENT ON COLUMN export_task.task_type IS '类型: cost_report/token_report/audit_log/model_report';
COMMENT ON COLUMN export_task.status IS '状态: pending/processing/completed/failed';

-- ============================================================
-- 索引管理函数
-- ============================================================

-- 创建分区维护函数（每月自动创建新分区）
CREATE OR REPLACE FUNCTION create_api_request_log_partition()
RETURNS void AS $$
DECLARE
    partition_date DATE;
    partition_name TEXT;
    start_date TEXT;
    end_date TEXT;
BEGIN
    partition_date := DATE_TRUNC('month', NOW()) + INTERVAL '1 month';
    partition_name := 'api_request_log_' || TO_CHAR(partition_date, 'YYYY_MM');
    start_date := TO_CHAR(partition_date, 'YYYY-MM-DD');
    end_date := TO_CHAR(partition_date + INTERVAL '1 month', 'YYYY-MM-DD');

    EXECUTE FORMAT(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF api_request_log
         FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );
END;
$$ LANGUAGE plpgsql;