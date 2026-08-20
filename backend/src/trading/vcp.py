"""VCP 识别 + 关键价位 + 买区状态机 — SEPA 口径 (spec 2026-08-20 §1.4-§1.6).

纯函数, 无 IO。60 交易日回看窗:
- zigzag 段阈值 >=4% (swing high -> swing low 为一段收缩)
- >=2 次收缩, 深度单调递减 (后段 <= 前段 x0.8)
- 基部总深度 <=35%, 末端量能 (5 日均量 <= 50 日均量 x0.6)
- pivot = 基部内最高价 (各收缩段 swing high 的最大值, 结构口径, 不随末端突破漂移);
  买区 = [pivot, pivot x1.05]; 止损 = max(最近 swing low, pivot x0.92)
状态机: in_buy_zone (收盘在买区) / near_buy_zone (距下沿 <=3%) / watch (其余)。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]

VCP_WINDOW = 60  # 回看窗 (交易日)
ZIGZAG_PCT = 0.04  # zigzag 反转确认幅度
MIN_CONTRACTIONS = 2  # 最少收缩次数
DECAY_RATIO = 0.8  # 后段深度 <= 前段 x0.8
MAX_BASE_DEPTH = 0.35  # 基部总深度上限
DRYUP_RATIO = 0.6  # 末端量能/50日均量 上限
BUY_ZONE_UPPER = 1.05  # 买区上沿 = pivot x1.05
NEAR_ZONE_LOWER = 0.97  # near_buy_zone: 距买区下沿 <=3%
STOP_FLOOR_RATIO = 0.92  # 止损下限 = pivot x0.92
DRYUP_VOL_WINDOW = 50  # 末端量能基准窗
QUALITY_W_CNT, QUALITY_W_STEEP, QUALITY_W_DRY = 0.3, 0.4, 0.3  # 质量分权重


@dataclass(frozen=True)
class Pivot:
    """zigzag 转折点。"""

    idx: int
    price: float
    kind: str  # 'H' | 'L'


@dataclass(frozen=True)
class VcpResult:
    """VCP 识别结果 + 关键价位 + 状态 (spec §2.3 candidates.vcp 与价位字段)。"""

    contractions: int
    depths: list[float]  # 各收缩段深度 (0-1)
    depth_pct: float  # 基部总深度 (0-1)
    quality: float  # 质量分 0-1
    volume_dryup: bool
    pivot: float
    buy_zone_low: float
    buy_zone_high: float
    stop: float
    state: str  # in_buy_zone | near_buy_zone | watch


def zigzag(x: Array, pct: float = ZIGZAG_PCT) -> list[Pivot]:
    """阈值反转 zigzag: 反向波动 >=pct 时确认上一极值并换向。

    末端未确认的进行中极值也纳入 (止损需要"最近 swing low")。
    初始方向视为向上: 窗首即下跌段时起点即局部高点, 与 VCP 下行结构一致。
    """
    if len(x) == 0:
        return []
    pivots: list[Pivot] = []
    direction = 1  # 1: 向上段 (track 高点), -1: 向下段 (track 低点)
    ext_idx, ext_val = 0, float(x[0])
    for i in range(1, len(x)):
        v = float(x[i])
        if direction == 1:
            if v >= ext_val:
                ext_idx, ext_val = i, v
            elif ext_val > 0 and (ext_val - v) / ext_val >= pct:
                pivots.append(Pivot(ext_idx, ext_val, 'H'))
                direction, ext_idx, ext_val = -1, i, v
        else:
            if v <= ext_val:
                ext_idx, ext_val = i, v
            elif ext_val > 0 and (v - ext_val) / ext_val >= pct:
                pivots.append(Pivot(ext_idx, ext_val, 'L'))
                direction, ext_idx, ext_val = 1, i, v
    pivots.append(Pivot(ext_idx, ext_val, 'H' if direction == 1 else 'L'))
    return pivots


def classify_state(close: float, pivot: float) -> str:
    """买区状态机: 收盘在 [pivot, 1.05x] 内 = in_buy_zone; 距下沿 <=3% = near; 其余 watch。"""
    if pivot <= 0:
        return 'watch'
    if pivot <= close <= pivot * BUY_ZONE_UPPER:
        return 'in_buy_zone'
    if pivot * NEAR_ZONE_LOWER <= close < pivot:
        return 'near_buy_zone'
    return 'watch'


def is_one_word_limit_up(o: float, h: float, l: float, c: float, prev_close: float) -> bool:
    """一字涨停板 (o=h=l=c 且涨幅 >=9.5%) — 触及买区也无法买入, 供 limit_up_unexecutable。"""
    same = abs(h - l) < 1e-6 and abs(c - o) < 1e-6
    return same and prev_close > 0 and c >= prev_close * 1.095


def _quality(n: int, depths: list[float], vol_ratio: float) -> float:
    """VCP 质量分 (0-1): 收缩次数(30%) + 递减陡峭度(40%) + 量能萎缩度(30%)。"""
    cnt_score = min(n, 4) / 4.0  # 4 次及以上满分
    ratios = [depths[k + 1] / depths[k] for k in range(len(depths) - 1)]
    mean_r = float(np.mean(ratios))  # 门槛已保证 <=DECAY_RATIO, 越小越陡
    steep = float(np.clip((DECAY_RATIO - mean_r) / DECAY_RATIO, 0.0, 1.0))
    dry = float(np.clip((DRYUP_RATIO - vol_ratio) / DRYUP_RATIO, 0.0, 1.0))
    return round(QUALITY_W_CNT * cnt_score + QUALITY_W_STEEP * steep + QUALITY_W_DRY * dry, 4)


def find_vcp(close: Array, volume: Array) -> VcpResult | None:
    """60 日窗 VCP 识别; 不满足任一门槛返回 None。

    zigzag/深度/基部均用收盘价口径; pivot 取各收缩段 swing high 最大值 (结构高点)。
    """
    c_win = close[-VCP_WINDOW:]
    v_win = volume[-VCP_WINDOW:]
    if len(c_win) < 2:
        return None
    pivots = zigzag(c_win)

    # 收缩段: 相邻 H->L pivot 对
    highs: list[float] = []
    lows: list[float] = []
    for a, b in itertools.pairwise(pivots):
        if a.kind == 'H' and b.kind == 'L':
            highs.append(a.price)
            lows.append(b.price)
    n = len(highs)
    if n < MIN_CONTRACTIONS:
        return None
    depths = [(h - l) / h for h, l in zip(highs, lows)]  # zigzag 反转阈值保证 h > l, 深度恒正
    # 深度单调递减: 后段 <= 前段 x0.8 (逐对检查)
    if any(depths[k + 1] > depths[k] * DECAY_RATIO for k in range(n - 1)):
        return None

    # 基部: pivot = 收缩段 swing high 最大值; 低点含末端收盘 (未确认极值)
    pivot = max(highs)
    base_low = min(lows + [float(c_win[-1])])
    depth_pct = (pivot - base_low) / pivot
    if depth_pct > MAX_BASE_DEPTH:
        return None

    # 末端量能: 最近 5 日均量 <= 50 日均量 x0.6 (窗内不足 50 取全部)
    if len(v_win) == 0 or float(np.mean(v_win)) <= 0:
        return None
    v5 = float(np.mean(v_win[-5:]))
    v50 = float(np.mean(v_win[-DRYUP_VOL_WINDOW:]))
    if v50 <= 0:
        return None
    vol_ratio = v5 / v50
    volume_dryup = vol_ratio <= DRYUP_RATIO
    if not volume_dryup:
        return None

    # 止损 = max(最近 swing low, pivot x0.92); 最近 L 含未确认末端极值
    last_lows = [p.price for p in pivots if p.kind == 'L']
    structural_stop = last_lows[-1] if last_lows else base_low
    stop = max(structural_stop, pivot * STOP_FLOOR_RATIO)

    c_last = float(c_win[-1])
    return VcpResult(
        contractions=n,
        depths=[round(d, 4) for d in depths],
        depth_pct=round(depth_pct, 4),
        quality=_quality(n, depths, vol_ratio),
        volume_dryup=volume_dryup,
        pivot=round(pivot, 4),
        buy_zone_low=round(pivot, 4),
        buy_zone_high=round(pivot * BUY_ZONE_UPPER, 4),
        stop=round(stop, 4),
        state=classify_state(c_last, pivot),
    )
