"""测试辅助工具：构造可安全模拟 ORM 实体/行对象的 mock。

说明：
unittest.mock.MagicMock(name="xx") 中 `name` 是保留参数（用于给 mock 起显示名），
不会成为可访问的 .name 属性，导致 `_to_response` 等序列化逻辑取到子 mock。
本 helper 先创建裸 MagicMock，再通过 setattr 写入全部属性，
保留 MagicMock 的属性自动补全能力（service 层多取几个字段也不会崩），
同时 name/id/status 等都能按预期值返回。
"""
from unittest.mock import MagicMock


def mock_orm(**attrs) -> MagicMock:
    """构造一个属性行为类似 ORM 行对象的 MagicMock。"""
    m = MagicMock()
    for key, value in attrs.items():
        setattr(m, key, value)
    return m
