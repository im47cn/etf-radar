"""贵金属指标纯函数 — 全部 as-of friendly (t 时点只依赖截至 t 的数据).

口径与 scripts/research/gsr_timing_backtest.py 预注册回测一致:
金银比 = GLD/SLV 收盘价比, 分位窗口 1260 交易日 (5y), 分位含自身.
回测结论 (2026-08-19): 择时无 alpha, 这些指标仅作描述性展示.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]

GSR_WINDOW = 1260  # 5y 分位窗口, 与回测口径一致


def gold_silver_ratio(gld: Array, slv: Array) -> Array:
    """金银比序列 (GLD/SLV 收盘价比; ETF 比值与真金银比差常数乘数, 分位不受影响)."""
    return gld / slv


def rolling_percentile(x: Array, window: int) -> Array:
    """每个时点, 当前值在 trailing window 内的分位 (含自身); burn-in 前为 nan."""
    out: Array = np.full(len(x), np.nan)
    for i in range(window - 1, len(x)):
        w = x[i - window + 1 : i + 1]
        out[i] = float((w <= w[-1]).mean())
    return out


def daily_change(x: Array) -> Array:
    """日变化量 (价格序列的一阶差分; 首位为 nan)."""
    out: Array = np.full(len(x), np.nan)
    out[1:] = x[1:] - x[:-1]
    return out


def rolling_corr(a: Array, b: Array, window: int) -> Array:
    """trailing window 内 a/b 日变化的 Pearson 相关; 样本不足或零方差为 nan."""
    da, db = daily_change(a), daily_change(b)
    out: Array = np.full(len(a), np.nan)
    for i in range(window, len(a)):
        wa, wb = da[i - window + 1 : i + 1], db[i - window + 1 : i + 1]
        sa, sb = wa.std(), wb.std()
        if sa > 0 and sb > 0:
            # clip 防浮点误差越界 (corr 可能算出 1.0000000000000004, 违反 schema [-1,1])
            out[i] = float(np.clip(((wa - wa.mean()) * (wb - wb.mean())).mean() / (sa * sb), -1.0, 1.0))
    return out


def simple_return(x: Array, n: int) -> float:
    """最近 n 期简单收益率 (x[-1]/x[-n-1] - 1); 数据不足抛 ValueError."""
    if len(x) < n + 1:
        raise ValueError(f'simple_return needs {n + 1} points, got {len(x)}')
    return float(x[-1] / x[-n - 1] - 1.0)


def change_over(x: Array, n: int) -> float:
    """水平值 n 期变化 (x[-1] - x[-n-1]); 用于利率这类水平序列."""
    if len(x) < n + 1:
        raise ValueError(f'change_over needs {n + 1} points, got {len(x)}')
    return float(x[-1] - x[-n - 1])
