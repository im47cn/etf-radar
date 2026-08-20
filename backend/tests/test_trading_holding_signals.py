"""holding_signals 单测 — spec §1.8 全量口径夹具验证 (纯函数, 合成 bars)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from src.trading.holding_signals import Holding, compute_holding_signals

AS_OF = date(2026, 8, 20)


def geo(n: int, start: float = 10.0, daily: float = 1.004) -> list[float]:
    return [start * daily**i for i in range(n)]


def mk_bars(
    closes: list[float],
    end: date = AS_OF,
    o: float | None = None,
    h: float | None = None,
    l: float | None = None,
) -> list[dict[str, float | str]]:
    """收盘序列 -> M0 bars (末根对齐 end=as_of); o/h/l 缺省 = 收盘 (即 o=h=l=c, 供一字板夹具)。"""
    out = []
    n = len(closes)
    for i, c in enumerate(closes):
        out.append(
            {
                'd': (end - timedelta(days=n - 1 - i)).isoformat(),
                'o': o if o is not None else c,
                'h': h if h is not None else c,
                'l': l if l is not None else c,
                'c': c,
                'v': 1e6,
                'amt': 2e8,
            }
        )
    return out


def mk_hold(code: str = '600519', cost: float = 10.0, stop: float | None = None) -> Holding:
    return Holding(code=code, name='测试股', shares=100, avg_cost=cost, stop_current=stop)


def types_of(res) -> set[str]:
    return {e.type for e in res.events}


# ---------- 止损上移 (只上移) ----------

def test_stop_update_to_cost_at_10pct_profit() -> None:
    # 60 根缓涨到 11.5, 成本 10 (+15%) -> 抬至成本价 10; 现 stop 9.2 更低 -> 输出
    bars = mk_bars(geo(60, 10.0, 1.0023))  # 末值 ~11.5
    res = compute_holding_signals(mk_hold(cost=10.0, stop=9.2), bars, None, AS_OF)
    ev = [e for e in res.events if e.type == 'stop_update']
    assert len(ev) == 1
    assert '成本价' in ev[0].message
    assert res.suggested_stop == pytest.approx(10.0)
    assert res.health == 'warning'


def test_stop_update_trail_ma50_at_20pct_profit() -> None:
    # 60 根涨到 12.5 (+25%) -> 跟随 50MA; ma50 > 现 stop -> 上移到 ma50
    closes = geo(60, 10.0, 1.0037)
    bars = mk_bars(closes)
    ma50 = float(np.mean(closes[-50:]))
    res = compute_holding_signals(mk_hold(cost=10.0, stop=9.0), bars, None, AS_OF)
    ev = [e for e in res.events if e.type == 'stop_update']
    assert len(ev) == 1
    assert '跟随50日均线' in ev[0].message
    assert res.suggested_stop == pytest.approx(ma50, rel=1e-3)


def test_stop_never_moves_down() -> None:
    # 浮盈 15% -> 目标成本 10, 但现止损 10.5 已更高: 只上移 -> 不输出
    bars = mk_bars(geo(60, 10.0, 1.0023))
    res = compute_holding_signals(mk_hold(cost=10.0, stop=10.5), bars, None, AS_OF)
    assert 'stop_update' not in types_of(res)
    assert res.suggested_stop is None


def test_stop_update_first_stop_when_none() -> None:
    # 从未设止损 + 浮盈 15% -> 首次建议成本价
    bars = mk_bars(geo(60, 10.0, 1.0023))
    res = compute_holding_signals(mk_hold(cost=10.0, stop=None), bars, None, AS_OF)
    assert 'stop_update' in types_of(res)
    assert res.suggested_stop == pytest.approx(10.0)


def test_no_stop_update_below_10pct_profit() -> None:
    closes = geo(60, 10.0, 1.0023)
    bars = mk_bars(closes)
    res = compute_holding_signals(mk_hold(cost=float(closes[-1]), stop=None), bars, None, AS_OF)
    assert res.health == 'holding'
    assert res.events == []
    assert res.profit_pct == pytest.approx(0.0, abs=0.01)


def test_trail_ma50_requires_ma50_available() -> None:
    # 浮盈 >=20% 但 bars<50 无 50MA -> 跟随无从谈起, 不输出
    closes = geo(49, 10.0, 1.02)  # 末值 ~25.4, +154% 浮盈
    bars = mk_bars(closes)
    res = compute_holding_signals(mk_hold(cost=10.0, stop=None), bars, None, AS_OF)
    assert 'stop_update' not in types_of(res)


# ---------- 收盘跌破 50 日均线 (穿越判定) ----------

def test_break_ma50_on_cross_below() -> None:
    # 60 根上涨后末根大跌穿 50MA (昨收 >= 昨 50MA)
    closes = geo(60, 10.0, 1.005)
    closes[-1] = closes[-2] * 0.8
    bars = mk_bars(closes)
    res = compute_holding_signals(mk_hold(cost=float(closes[-2]), stop=None), bars, None, AS_OF)
    assert 'break_ma50' in types_of(res)
    assert any(e.message == '收盘跌破 50 日均线' for e in res.events)


def test_no_break_event_when_already_below() -> None:
    # 早已在 50MA 下方运行 (持续阴跌): 昨收 < 昨 50MA -> 非穿越, 不重复告警
    closes = [20.0 - i * 0.3 for i in range(60)]
    bars = mk_bars(closes)
    res = compute_holding_signals(mk_hold(cost=20.0, stop=None), bars, None, AS_OF)
    assert 'break_ma50' not in types_of(res)


# ---------- 阶段转为 Stage 3/4 ----------

def test_stage_change_to_3() -> None:
    # 260 根强涨 (Stage 2, 模板 7/8) 后末根大跌 -> pass 掉到 5 且价仍高于 200MA -> Stage 3
    # (根数须 >250: 昨日截断序列也要 >= MIN_BARS, 否则 stage_prev=None 事件不触发)
    closes = geo(260, 10.0, 1.004)
    closes[-1] = closes[-2] * 0.70
    bars = mk_bars(closes)
    res = compute_holding_signals(mk_hold(cost=float(closes[-1] / 1.02), stop=None), bars, None, AS_OF)
    assert 'stage_change' in types_of(res)
    assert any('阶段转为 Stage 3' in e.message for e in res.events)


def test_no_stage_change_when_stable() -> None:
    closes = geo(260, 10.0, 1.004)
    bars = mk_bars(closes)
    res = compute_holding_signals(mk_hold(cost=float(closes[-1]), stop=None), bars, None, AS_OF)
    assert 'stage_change' not in types_of(res)


def test_candidate_rs_pct_used_when_in_pool() -> None:
    # 持仓股在候选池: trading_doc 提供 rs_pct -> 第 7 条参与判定 (走 candidate 分支)
    closes = geo(260, 10.0, 1.004)
    closes[-1] = closes[-2] * 0.70
    bars = mk_bars(closes)
    doc = {
        'candidates': [
            {'code': '600519', 'name': '测试股', 'rs_pct': 85.0, 'state': 'watch'}
        ]
    }
    res = compute_holding_signals(mk_hold(), bars, doc, AS_OF)
    assert res.code == '600519'  # 走通 candidate 分支不抛错
    # 持仓股不在候选池 (循环无匹配) -> rs 缺省, 不抛错
    res2 = compute_holding_signals(mk_hold(code='000002'), bars, doc, AS_OF)
    assert res2.code == '000002'


# ---------- 跌停止损待执行 ----------

def _limit_down_bars() -> list[dict[str, float | str]]:
    # 昨收 9.0, 今一字跌停 8.0 (o=h=l=c, -11.1%)
    return mk_bars([9.0, 8.0], o=8.0, h=8.0, l=8.0)


def test_stop_pending_on_limit_down_at_stop() -> None:
    bars = _limit_down_bars()
    res = compute_holding_signals(mk_hold(cost=9.0, stop=8.5), bars, None, AS_OF)
    assert 'stop_pending' in types_of(res)
    assert any('止损待执行' in e.message for e in res.events)


def test_no_stop_pending_above_stop_level() -> None:
    # 一字跌停但收盘仍高于止损位 -> 无待执行标记
    bars = _limit_down_bars()
    res = compute_holding_signals(mk_hold(cost=9.0, stop=7.0), bars, None, AS_OF)
    assert 'stop_pending' not in types_of(res)


def test_no_stop_pending_without_initial_stop() -> None:
    bars = _limit_down_bars()
    res = compute_holding_signals(mk_hold(cost=9.0, stop=None), bars, None, AS_OF)
    assert 'stop_pending' not in types_of(res)


# ---------- 停牌冻结 ----------

def test_suspended_frozen_when_no_bar_today() -> None:
    bars = mk_bars([10.0, 10.2, 10.5], end=date(2026, 8, 17))  # 末根 08-17 < as_of 08-20
    res = compute_holding_signals(mk_hold(cost=10.0, stop=9.5), bars, None, AS_OF)
    assert res.health == 'frozen'
    assert types_of(res) == {'suspended'}
    assert '停牌' in res.events[0].message
    assert res.profit_pct is None
    assert res.close == pytest.approx(10.5)


def test_empty_bars_frozen() -> None:
    res = compute_holding_signals(mk_hold(), [], None, AS_OF)
    assert res.health == 'frozen'
    assert res.close is None
    assert res.events[0].type == 'suspended'


# ---------- 综合输出字段 ----------

def test_profit_pct_and_close_reported() -> None:
    closes = geo(60, 10.0, 1.0023)
    bars = mk_bars(closes)
    res = compute_holding_signals(mk_hold(cost=10.0, stop=None), bars, None, AS_OF)
    assert res.close == pytest.approx(closes[-1])
    assert res.profit_pct == pytest.approx((closes[-1] / 10.0 - 1) * 100, rel=1e-3)
