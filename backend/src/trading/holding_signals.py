"""持仓管理信号 — SEPA 口径 (spec 2026-08-20 §1.8, 纯函数无 IO).

每日 EOD 对每笔持仓重算, 全部事实性文案 (合规立场 B):
- 止损只上移: 浮盈 >=10% -> 抬至成本价; >=20% -> 跟随 50MA; 均仅当高于现止损位时输出
- 收盘跌破 50 日均线 (穿越判定: 昨收 >= 昨 50MA 且今收 < 今 50MA, 防每日重复告警)
- 阶段转为 Stage 3/4 (昨日 stage != 今日 stage 且今日 in {3,4})
- 一字跌停且收盘 <= 止损位 -> "止损待执行" (跌停无法卖出)
- 停牌 (末根 bar 日期 < as_of) -> 冻结该持仓信号, 不再计算其他事件

health: holding (无事件) | warning (含事件) | frozen (停牌冻结)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from .trend import compute_trend, sma

PROFIT_STOP_TO_COST = 0.10  # 浮盈 >=10%: 止损抬至成本价
PROFIT_STOP_TRAIL_MA50 = 0.20  # 浮盈 >=20%: 止损跟随 50MA
LIMIT_DOWN_PCT = 0.905  # 一字跌停近似: 收盘 <= 昨收 x0.905 且 o=h=l=c (对称 vcp 一字涨停口径)


@dataclass(frozen=True)
class Holding:
    """持仓 (M3 事件流推导产物, 字段对齐 frontend Position)。"""

    code: str
    name: str
    shares: int
    avg_cost: float
    stop_current: float | None


@dataclass(frozen=True)
class SignalEvent:
    """单条信号事件 (type 稳定枚举, message 为事实性文案)。"""

    type: str  # stop_update | break_ma50 | stage_change | stop_pending | suspended
    message: str


@dataclass(frozen=True)
class HoldingSignalResult:
    """单持仓信号输出。"""

    code: str
    name: str
    health: str  # holding | warning | frozen
    close: float | None
    profit_pct: float | None  # (close-avg_cost)/avg_cost, 冻结时 None
    suggested_stop: float | None  # stop_update 事件的新止损位, 其余 None
    events: list[SignalEvent] = field(default_factory=list)


def _bars_arrays(bars: list[dict[str, Any]]) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray]:
    """M0 bars -> (dates, high, low, close) numpy 数组 (升序原样)。"""
    dates = [str(b['d']) for b in bars]
    high = np.array([float(b['h']) for b in bars], dtype=np.float64)
    low = np.array([float(b['l']) for b in bars], dtype=np.float64)
    close = np.array([float(b['c']) for b in bars], dtype=np.float64)
    return dates, high, low, close


def _candidate_of(trading_doc: dict[str, Any] | None, code: str) -> dict[str, Any] | None:
    """从 trading.json candidates 取该股条目 (可能不在候选池)。"""
    if not trading_doc:
        return None
    for cand in trading_doc.get('candidates', []):
        if str(cand.get('code')) == code:
            return {str(k): v for k, v in cand.items()}
    return None


def _stage_of(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, rs_pct: float | None
) -> int | None:
    """当前趋势阶段 (截断后序列的末根判定); bars<250 或价格非法 -> None。"""
    result = compute_trend(high, low, close, rs_pct)
    return result.stage if result else None


def _stop_update_event(
    close: float, avg_cost: float, stop_current: float | None, ma50: float | None
) -> tuple[SignalEvent, float] | None:
    """止损上移建议 (spec §1.8 只上移); 无建议返回 None。"""
    profit = (close - avg_cost) / avg_cost if avg_cost > 0 else 0.0
    target: float | None = None
    label = ''
    if profit >= PROFIT_STOP_TRAIL_MA50:
        if ma50 is None:
            return None  # bars 不足无法算 50MA, 跟随无从谈起
        target, label = ma50, '跟随50日均线'
    elif profit >= PROFIT_STOP_TO_COST:
        target, label = avg_cost, '成本价'
    if target is None or target <= 0:
        return None
    new_stop = max(target, stop_current) if stop_current is not None else target
    if stop_current is not None and new_stop <= stop_current:
        return None  # 只上移: 不高于现止损位则不输出
    pct = profit * 100
    return (
        SignalEvent('stop_update', f'浮盈 {pct:.1f}%，止损位参考 {new_stop:.2f}（{label}）'),
        round(new_stop, 4),
    )


def _is_one_word_limit_down(o: float, h: float, l: float, c: float, prev_close: float) -> bool:
    """一字跌停 (o=h=l=c 且跌幅 >=9.5%) — 无法卖出, 对称 vcp.is_one_word_limit_up。"""
    same = abs(h - l) < 1e-6 and abs(c - o) < 1e-6
    return same and prev_close > 0 and c <= prev_close * LIMIT_DOWN_PCT


def compute_holding_signals(
    holding: Holding,
    bars: list[dict[str, Any]],
    trading_doc: dict[str, Any] | None,
    as_of: date,
) -> HoldingSignalResult:
    """单持仓信号计算 (spec §1.8 全量口径)。

    bars: M0 ohlcv 格式 [{d,o,h,l,c,v,amt}] 日期升序; trading_doc: trading.json 内容。
    """
    empty = HoldingSignalResult(
        code=holding.code,
        name=holding.name,
        health='frozen',
        close=None,
        profit_pct=None,
        suggested_stop=None,
        events=[SignalEvent('suspended', '无行情数据，信号冻结')],
    )
    if not bars:
        return empty

    dates, high, low, close_arr = _bars_arrays(bars)
    as_of_iso = as_of.isoformat()
    if dates[-1] < as_of_iso:
        # 停牌: 当日无 bar, 冻结该持仓信号 (spec §1.8)
        return HoldingSignalResult(
            code=holding.code,
            name=holding.name,
            health='frozen',
            close=float(close_arr[-1]),
            profit_pct=None,
            suggested_stop=None,
            events=[SignalEvent('suspended', f'停牌（最新行情 {dates[-1]}），信号冻结')],
        )

    events: list[SignalEvent] = []
    c = float(close_arr[-1])
    prev_close = float(close_arr[-2]) if len(close_arr) >= 2 else None
    profit = (c - holding.avg_cost) / holding.avg_cost if holding.avg_cost > 0 else None

    # 1) 止损上移建议 (只上移)
    ma50_arr = sma(close_arr, 50)
    ma50 = float(ma50_arr[-1]) if len(close_arr) >= 50 and not np.isnan(ma50_arr[-1]) else None
    upd = _stop_update_event(c, holding.avg_cost, holding.stop_current, ma50)
    suggested: float | None = None
    if upd:
        events.append(upd[0])
        suggested = upd[1]

    # 2) 收盘跌破 50 日均线 (穿越判定, 防持续处下方时每日重复)
    if ma50 is not None and len(close_arr) >= 51:
        ma50_prev = float(ma50_arr[-2])
        if prev_close is not None and prev_close >= ma50_prev and c < ma50:
            events.append(SignalEvent('break_ma50', '收盘跌破 50 日均线'))

    # 3) 阶段转为 Stage 3/4 (昨日 vs 今日; rs_pct 取候选池横截面, 持仓股不在池内则 None)
    cand = _candidate_of(trading_doc, holding.code)
    rs_pct = cand.get('rs_pct') if cand else None
    rs = float(rs_pct) if isinstance(rs_pct, (int, float)) else None
    stage_today = _stage_of(high, low, close_arr, rs)
    stage_prev = _stage_of(high[:-1], low[:-1], close_arr[:-1], rs) if len(close_arr) > 1 else None
    if (
        stage_today in (3, 4)
        and stage_prev is not None
        and stage_prev != stage_today
    ):
        events.append(SignalEvent('stage_change', f'阶段转为 Stage {stage_today}'))

    # 4) 跌停无法卖出 -> 止损待执行 (仅当收盘已到/破止损位)
    if prev_close is not None and holding.stop_current is not None:
        o = float(bars[-1]['o'])
        if _is_one_word_limit_down(o, float(high[-1]), float(low[-1]), c, prev_close) and c <= holding.stop_current:
            events.append(SignalEvent('stop_pending', '跌停无法卖出，止损待执行'))

    return HoldingSignalResult(
        code=holding.code,
        name=holding.name,
        health='warning' if events else 'holding',
        close=c,
        profit_pct=round(profit * 100, 2) if profit is not None else None,
        suggested_stop=suggested,
        events=events,
    )
