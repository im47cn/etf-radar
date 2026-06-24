"""龙头标签规则（仅作提示，不替代用户判断）。

设计：
- 量比作为单日噪声指标，不进入长期"龙头"判定，仅作辅助列展示
- RSI 仅作"未超买"过滤器，避免追高
- 缺失数据下退化到 strength-only 规则，避免一刀切置空
"""
from __future__ import annotations


def classify_leader(
    strength_60d: int | None,
    rsi_14: float | None,
) -> str:
    """返回龙头标签字符串。

    规则：
      strength_60d 为 None → ''
      RSI 为 None → strength ≥ 70 给 '⭐'，否则 ''
      strength ≥ 90 且 RSI ∈ [50, 70] → '⭐⭐⭐'
      strength ≥ 80 且 RSI ∈ [45, 70] → '⭐⭐'
      strength ≥ 70 → '⭐'
      其他 → ''
    """
    if strength_60d is None:
        return ''
    if rsi_14 is None:
        return '⭐' if strength_60d >= 70 else ''
    if strength_60d >= 90 and 50.0 <= rsi_14 <= 70.0:
        return '⭐⭐⭐'
    if strength_60d >= 80 and 45.0 <= rsi_14 <= 70.0:
        return '⭐⭐'
    if strength_60d >= 70:
        return '⭐'
    return ''
