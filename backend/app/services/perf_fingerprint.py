"""压测任务的参数指纹。

用途：判定两个压测任务是否「严格可比」。
  * 指纹相同 → 负载参数完全一致，指标可直接横向对比
  * 指纹不同 → 仍允许对比，但前端需标红提示差异项

只纳入**影响负载本身**的参数；任务名、备注等不纳入。
"""
import hashlib
from typing import Any, Optional

# 参与指纹计算的影响项（顺序固定，不可随意调整，否则历史指纹失效）
_FINGERPRINT_FIELDS = (
    "model_id",
    "mode",
    "parallel",
    "rate",
    "number",
    "dataset_type",
    "input_length",
    "output_length",
    "stream",
)

# 差异提示用的中文名（顺序与 _FINGERPRINT_FIELDS 对应）
FIELD_LABELS = {
    "model_id": "目标模型",
    "mode": "压测模式",
    "parallel": "并发数",
    "rate": "目标 RPS",
    "number": "总请求数",
    "dataset_type": "数据集",
    "input_length": "输入长度",
    "output_length": "输出长度",
    "stream": "流式模式",
}


def _normalize(value: Any) -> str:
    """把各种值归一化成稳定的字符串，避免 None / 0 / False 混淆。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        # 避免 20.0 与 20 产生不同指纹
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _get(obj: Any, field: str) -> Any:
    """兼容 dict 与 ORM 对象两种入参。"""
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def compute_fingerprint(task: Any) -> str:
    """计算参数指纹（SHA256 前 32 位）。

    Args:
        task: 具备 _FINGERPRINT_FIELDS 中字段的 dict 或 ORM 对象

    Returns:
        32 位十六进制字符串
    """
    parts = [_normalize(_get(task, f)) for f in _FINGERPRINT_FIELDS]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def diff_fingerprint_fields(a: Any, b: Any) -> list[str]:
    """返回两个任务在指纹相关字段上的差异项中文名列表（空列表 = 完全一致）。"""
    diffs: list[str] = []
    for field in _FINGERPRINT_FIELDS:
        if _normalize(_get(a, field)) != _normalize(_get(b, field)):
            diffs.append(FIELD_LABELS.get(field, field))
    return diffs
