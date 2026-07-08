"""latest no-regress 护栏: 陈旧 run 不得用更旧数据覆盖较新的 data/latest。

回退判定基于 meta 的 cn_data_date / us_data_date(ISO YYYY-MM-DD, 可字典序比较)。
任一市场新数据严格早于现有 latest → 判定回退, 调用方应跳过写入, 保留上一好版本。
陈旧暴露交由 C1 哨兵告警 + 前端 UpdateBadge 老化, 本护栏只保证 latest 单调不倒退。
"""
from __future__ import annotations

from typing import Any

_MARKETS = ('cn', 'us')


def should_write_latest(
    new_meta: dict[str, Any], existing_meta: dict[str, Any] | None
) -> tuple[bool, str]:
    """决定是否用 new_meta 对应的产出覆盖现有 latest。

    Returns (ok, reason):
      - existing_meta 为 None/空(首次)→ (True, 'first')
      - 任一市场 new_date < existing_date(严格更旧)→ (False, 'regress:<market>')
      - 否则(同日或更新)→ (True, 'ok')

    某侧 date 缺失(None/'')→ 该侧不参与判定(向后兼容, 保守放行)。
    """
    if not existing_meta:
        return True, 'first'
    for market in _MARKETS:
        key = f'{market}_data_date'
        new_d = new_meta.get(key)
        old_d = existing_meta.get(key)
        if new_d and old_d and new_d < old_d:
            return False, f'regress:{market}'
    return True, 'ok'
