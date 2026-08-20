"""筛选漏斗 + RS 分位 + 综合分 — SEPA 口径 (spec 2026-08-20 §1.3).

漏斗: 全市场 -> 剔 ST/退市/次新(<250 bars)/价<3 元/20 日均成交额<1 亿 -> 模板>=6 且
Stage 2 -> VCP -> 综合分 Top 50。
综合分 (1-10): 模板(30%) + VCP 质量(40%) + RS 分位(20%) + 波动适配(10%);
vol 缺失时其权重并入 RS; RS 基准缺失时剔除 RS 项、剩余权重归一 (§1 综合分口径)。
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .trend import STAGE2_TEMPLATE_MIN, TEMPLATE_COUNT, compute_trend
from .vcp import find_vcp, is_one_word_limit_up

Array = NDArray[np.float64]

MIN_LIST_BARS = 250  # 上市 <250 交易日近似 (可用 bars 数)
MIN_PRICE = 3.0  # 收盘价下限 (元)
MIN_AMOUNT = 1e8  # 20 日日均成交额下限 (元)
TOP_N = 50  # 候选池上限
RS_WINDOW = 60  # RS 相对收益窗 (交易日)
RS_MIN_BARS = RS_WINDOW + 1
VOL_FIT_REF = 0.8  # 波动适配参考: 年化波动 80% 及以上记 0 分
W_TPL, W_VCP, W_RS, W_VOL = 0.3, 0.4, 0.2, 0.1  # 综合分权重 (§1)


@dataclass(frozen=True)
class StockBars:
    """单只个股对齐后的 OHLCV 数组 (qfq, 日期升序)。"""

    code: str
    open_: Array
    high: Array
    low: Array
    close: Array
    volume: Array
    amount: Array


def is_st(name: str) -> bool:
    """ST/*ST/退市整理标记 (名称含 'ST' 覆盖 *ST, '退' 覆盖退市整理)。"""
    upper = name.upper()
    return 'ST' in upper or '退' in name


def board_of(code: str) -> str | None:
    """板块映射: 60/00 主板, 30 创业板, 68 科创板; 其余 (北交所等) 不入漏斗。"""
    if code.startswith(('60', '00')):
        return 'main'
    if code.startswith('30'):
        return 'chinext'
    if code.startswith('68'):
        return 'star'
    return None


def r60(close: Array) -> float | None:
    """60 交易日简单收益; 数据不足或基准价非法返回 None。"""
    if len(close) < RS_MIN_BARS:
        return None
    base = float(close[-RS_MIN_BARS])
    if base <= 0:
        return None
    return float(close[-1]) / base - 1.0


def compute_rs_percentiles(r60_by_code: dict[str, float], bench_r60: float | None) -> dict[str, float]:
    """相对基准的超额 60 日收益在全市场横截面的百分位 (0-100, 含自身)。

    bench_r60 None (中证全指全 chain 失败) -> 空 dict, 上层降级。
    """
    if bench_r60 is None or not r60_by_code:
        return {}
    excess = {c: v - bench_r60 for c, v in r60_by_code.items()}
    vals = sorted(excess.values())
    n = len(vals)
    return {c: round(100.0 * bisect_right(vals, v) / n, 1) for c, v in excess.items()}


def composite_score(
    pass_count: int, vcp_quality: float, rs_pct: float | None, vol_forecast_ann: float | None
) -> float:
    """综合分 1-10。RS 缺 -> 剔除该项剩余归一; vol 缺 -> 权重并入 RS (§1 口径)。"""
    tpl = pass_count / TEMPLATE_COUNT
    if rs_pct is None:
        vol = None if vol_forecast_ann is None else float(np.clip(1.0 - vol_forecast_ann / VOL_FIT_REF, 0.0, 1.0))
        denom = W_TPL + W_VCP + (W_VOL if vol is not None else 0.0)
        num = W_TPL * tpl + W_VCP * vcp_quality + (W_VOL * vol if vol is not None else 0.0)
    elif vol_forecast_ann is None:
        denom = 1.0
        num = W_TPL * tpl + W_VCP * vcp_quality + (W_RS + W_VOL) * (rs_pct / 100.0)  # vol 并入 RS
    else:
        vol = float(np.clip(1.0 - vol_forecast_ann / VOL_FIT_REF, 0.0, 1.0))
        denom = 1.0
        num = W_TPL * tpl + W_VCP * vcp_quality + W_RS * (rs_pct / 100.0) + W_VOL * vol
    return round(10.0 * num / denom, 1)


def _is_tradable(bars: StockBars, name: str, board: str | None) -> bool:
    """漏斗第 1 层: 板块/ST/上市时长/价格/流动性。"""
    if board is None or is_st(name):
        return False
    if len(bars.close) < MIN_LIST_BARS:
        return False
    c = float(bars.close[-1])
    if c < MIN_PRICE or not np.isfinite(c) or c <= 0:
        return False
    amt20 = float(np.mean(bars.amount[-20:]))
    return bool(np.isfinite(amt20) and amt20 >= MIN_AMOUNT)


def screen_universe(
    universe: dict[str, StockBars],
    names: dict[str, str],
    rs_pct: dict[str, float],
    vol_by_code: dict[str, float | None],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """跑完整漏斗, 返回 (候选列表, 各层计数)。候选字段名与 §2.3 契约一致。"""
    stats = {'total': len(universe), 'tradable': 0, 'stage2': 0, 'vcp': 0, 'top': 0}
    cands: list[dict[str, Any]] = []
    for code, bars in universe.items():
        name = names.get(code, code)
        board = board_of(code)
        if not _is_tradable(bars, name, board):
            continue
        stats['tradable'] += 1
        trend = compute_trend(bars.high, bars.low, bars.close, rs_pct.get(code))
        if trend is None or trend.pass_count < STAGE2_TEMPLATE_MIN:
            continue  # 模板 >=6/8 即 Stage 2
        stats['stage2'] += 1
        vcp = find_vcp(bars.close, bars.volume)
        if vcp is None:
            continue
        stats['vcp'] += 1

        vol = vol_by_code.get(code)
        rs = rs_pct.get(code)
        o = float(bars.open_[-1])
        h = float(bars.high[-1])
        low = float(bars.low[-1])
        c = float(bars.close[-1])
        prev_c = float(bars.close[-2]) if len(bars.close) >= 2 else 0.0
        cands.append({
            'code': code,
            'name': name,
            'composite_score': composite_score(trend.pass_count, vcp.quality, rs, vol),
            'stage': trend.stage,
            'template_pass': trend.pass_count,
            'rs_pct': rs,
            'vcp': {
                'contractions': vcp.contractions,
                'depth_pct': round(vcp.depth_pct * 100.0, 1),
                'quality': vcp.quality,
                'volume_dryup': vcp.volume_dryup,
            },
            'pivot': vcp.pivot,
            'buy_zone_low': vcp.buy_zone_low,
            'buy_zone_high': vcp.buy_zone_high,
            'stop': vcp.stop,
            'state': vcp.state,
            'limit_up_unexecutable': is_one_word_limit_up(o, h, low, c, prev_c) and vcp.state == 'in_buy_zone',
            'chg_pct': round((c / prev_c - 1.0) * 100.0, 2) if prev_c > 0 else None,
            'board': board_of(code),
            'vol_forecast_ann': vol,
        })

    cands.sort(key=lambda x: (-x['composite_score'], x['code']))  # 分同则 code 稳定序
    top = cands[:TOP_N]
    stats['top'] = len(top)
    return top, stats
