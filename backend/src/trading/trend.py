"""趋势模板 8 条 + 四阶段状态机 — SEPA 口径 (spec 2026-08-20 §1.2/§2.1).

纯函数, 无 IO。个股与指数通用; 指数无 RS 横截面, 传 rs_pct=None (第 7 条恒 False)。
所有判据 as-of friendly: 只用截至末根 bar 的数据。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]

TEMPLATE_COUNT = 8
STAGE2_TEMPLATE_MIN = 6  # 模板 >=6/8 即 Stage 2
WEEKS_52 = 250  # 52 周约 250 交易日
MA200_SLOPE_WINDOW = 20  # 200MA 上行/走平判据窗口 (交易日)
FLAT_TOL = 0.004  # 20 日累计 0.4% (~0.02%/日) 以内视为走平
WRAP_TOL = 0.08  # |价-200MA|/200MA <= 8% 视为缠绕
MIN_BARS = 250  # 52 周高低 + MA200 斜率窗的最小 bar 数; 次新股由漏斗剔除


@dataclass(frozen=True)
class TrendResult:
    """单标的趋势判定结果 (criteria 按 §2.1 顺序)。"""

    criteria: list[bool]  # 8 条, False=未通过
    pass_count: int
    stage: int  # 1-4


def sma(x: Array, n: int) -> Array:
    """n 期简单均线; 前 n-1 位为 nan。"""
    out: Array = np.full(len(x), np.nan)
    if len(x) >= n > 0:
        c = np.cumsum(x)
        out[n - 1 :] = (c[n - 1 :] - np.concatenate(([0.0], c[:-n]))) / n
    return out


def classify_stage(
    c: float, ma200: float, ma200_prev20: float, pass_count: int
) -> int:
    """四阶段状态机 (spec §1.2), 判定顺序 2 -> 1 -> 4 -> 3。

    Stage 2: 模板 >=6/8; Stage 1: 价在 200MA +-8% 缠绕且 200MA 走平;
    Stage 4: 价 < 200MA 且 200MA 下行; Stage 3: 其余 (含涨后失守 50MA 且 200MA 走平)。
    """
    if pass_count >= STAGE2_TEMPLATE_MIN:
        return 2
    if ma200 > 0 and ma200_prev20 > 0:
        dist = abs(c - ma200) / ma200
        flat = abs(ma200 - ma200_prev20) / ma200_prev20 < FLAT_TOL
        if dist <= WRAP_TOL and flat:
            return 1
        if c < ma200 < ma200_prev20:
            return 4
    return 3


def compute_trend(high: Array, low: Array, close: Array, rs_pct: float | None) -> TrendResult | None:
    """模板 8 条 + 阶段一站式判定; bars<250 或价格非法时返回 None。

    均线与 52 周高低口径: 均线用收盘价, 52 周高低用 bar high/low (指数只有收盘,
    三个序列传同一份即可)。
    """
    n = len(close)
    if n < MIN_BARS:
        return None
    ma50 = float(sma(close, 50)[-1])
    ma150 = float(sma(close, 150)[-1])
    ma200_s = sma(close, 200)
    ma200 = float(ma200_s[-1])
    ma200_prev20 = float(ma200_s[-1 - MA200_SLOPE_WINDOW])  # n>=250 保证非 nan
    c = float(close[-1])
    if not (c > 0 and ma50 > 0 and ma150 > 0 and ma200 > 0):
        return None  # qfq 老股早期 ~0 价格护栏: 末值均线非法直接不评

    low_52w = float(np.min(low[-WEEKS_52:]))
    high_52w = float(np.max(high[-WEEKS_52:]))

    criteria = [
        c > ma50 and c > ma150 and c > ma200,  # 1 价 > 50/150/200MA
        ma150 > ma200,  # 2 150MA > 200MA
        ma200 > ma200_prev20,  # 3 200MA 至少 1 个月上行
        ma50 > ma150 and ma50 > ma200,  # 4 50MA > 150MA 且 > 200MA
        c >= low_52w * 1.30,  # 5 现价 >= 52 周低点 x1.30
        c >= high_52w * 0.75,  # 6 现价 >= 52 周高点 x0.75
        rs_pct is not None and rs_pct >= 70.0,  # 7 RS 分位 >= 70 (指数无 RS 恒 False)
        abs(ma50 - ma200) / ma200 >= 0.01,  # 8 非死亡交叉缠绕区 (50/200MA 距离 >=1%)
    ]
    pass_count = sum(criteria)
    return TrendResult(
        criteria=criteria,
        pass_count=pass_count,
        stage=classify_stage(c, ma200, ma200_prev20, pass_count),
    )
