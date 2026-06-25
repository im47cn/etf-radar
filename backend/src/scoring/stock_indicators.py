"""个股技术指标计算（RSI / 量比）"""
from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]
from ta.momentum import RSIIndicator  # type: ignore[import-untyped]


def compute_rsi(closes: list[float | None], period: int = 14) -> float | None:
    """Wilder's RSI(period) 使用 ta 库实现。

    不足 period+1 个有效收盘价时返回 None；
    ta 库结果为 NaN（如全等数据）时也返回 None。
    """
    series = pd.Series([c for c in closes if c is not None], dtype=float)
    if len(series) < period + 1:
        return None
    rsi = RSIIndicator(close=series, window=period, fillna=False).rsi()
    last = rsi.iloc[-1]
    if pd.isna(last):
        return None
    return round(float(last), 1)


def compute_volume_ratio(volumes: list[int | None]) -> float | None:
    """A 股标准量比：今日量 / 前 5 个交易日均量。

    要求 volumes 长度 ≥ 6，且：
      - volumes[-1] 不为 None
      - volumes[-6:-1] 中至少 5 个为正
      - 前 5 日均量 > 0
    """
    if len(volumes) < 6:
        return None
    today = volumes[-1]
    if today is None:
        return None
    prev_5 = [v for v in volumes[-6:-1] if v is not None and v > 0]
    if len(prev_5) < 5:
        return None
    mean_prev = sum(prev_5) / 5
    if mean_prev <= 0:
        return None
    return round(today / mean_prev, 2)
