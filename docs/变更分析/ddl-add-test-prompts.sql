-- 为已有 model_eval 表添加 test_prompts 字段（评测用户自定义测试 prompt 集）
ALTER TABLE model_eval ADD COLUMN IF NOT EXISTS test_prompts JSON DEFAULT NULL;