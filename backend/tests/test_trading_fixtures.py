"""SEPA trading 测试共享夹具 — 合成已知形态 bars (无测试函数, 供 test_trading_* 复用)。

形态构造约定:
- geo(n, start, daily): 几何上涨/下跌序列 (趋势形态)
- flat(n, price): 横盘序列
- legs 序列: [(high, low), ...] 每段线性高->低, 段间低->高衔接, 尾部爬到 tail_to (VCP 形态)
zigzag 段幅均 >=4% 且段内单调, 保证转折点价格精确可控。
"""
from __future__ import annotations

import numpy as np


def geo(n: int, start: float = 10.0, daily: float = 1.003) -> list[float]:
    return [start * daily**i for i in range(n)]


def flat(n: int, price: float = 50.0) -> list[float]:
    return [price] * n


def legs_series(
    legs: list[tuple[float, float]], bars_per_leg: int = 8, tail_to: float | None = None, tail_bars: int = 8
) -> list[float]:
    """收缩段序列: 每段 high->low 线性, 段间 low->下一 high 线性, 尾部低点->tail_to 线性。"""
    out: list[float] = []
    prev = legs[0][0]
    for high, low in legs:
        if prev != high:
            out.extend(np.linspace(prev, high, 3)[1:].tolist())  # 上一低点 -> 本段高点 (2 根)
        else:
            out.append(high)  # 首段: 序列即从高点起
        out.extend(np.linspace(high, low, bars_per_leg)[1:].tolist())  # 段内高 -> 低
        prev = low
    if tail_to is not None:
        out.extend(np.linspace(prev, tail_to, tail_bars)[1:].tolist())
    return out


def volumes(n: int, base: float = 1e6, tail: float = 4e5, tail_n: int = 5) -> np.ndarray:
    """量能序列: 前 n-tail_n 根 base, 尾部 tail_n 根 tail (默认满足 dryup <=0.6)。"""
    v = np.full(n, base)
    v[-tail_n:] = tail
    return v


def as_bars(
    closes: list[float], volume: np.ndarray | None = None, amount: float = 2e8
) -> dict[str, np.ndarray]:
    """收盘序列 -> 完整 bars 数组 (open/high/low 与 close 一致或微展宽)。"""
    c = np.array(closes, dtype=np.float64)
    return {
        'open': c.copy(),
        'high': c * 1.001,
        'low': c * 0.999,
        'close': c,
        'volume': volume if volume is not None else np.full(len(c), 1e6),
        'amount': np.full(len(c), amount),
    }


def candidate_closes(
    rise_n: int = 240, rise_daily: float = 1.003
) -> list[float]:
    """经典 SEPA 候选形态: 240 根上涨建势 (末值恰接 100) + 尾部 VCP 三段收缩, 末端近买区。

    VCP 段深度 25% -> 15.1% -> 7% 单调递减; pivot=100; 末端 98 (0.98x pivot -> near)。
    """
    start = 100.0 / rise_daily ** (rise_n - 1)  # 末根恰为 100.0, 与 VCP 高点无缝衔接
    rise = [start * rise_daily**i for i in range(rise_n)]
    vcp = legs_series([(100.0, 75.0), (93.0, 79.0), (86.0, 80.0)], tail_to=98.0)
    return rise + vcp


def offense_index(n: int = 400) -> list[float]:
    """进攻型指数序列 (无 RS 模板 7/8)。"""
    return geo(n, 3000.0, 1.002)


def moderate_index() -> list[float]:
    """中性型指数序列 (模板 5/8, 不够进攻也不至防守): 上涨后末段回撤 28%。"""
    rise = [10.0 * 1.003**i for i in range(380)]
    return rise + np.linspace(rise[-1], rise[-1] * 0.72, 20).tolist()


def defense_index(n: int = 400) -> list[float]:
    """防守型指数序列 (模板 1/8, 仅均线距离条成立)。"""
    return geo(n, 5000.0, 0.997)
