"""notify_digest 单测 — 迁移日报 + 周报组装 + ServerChan 推送 (mock send_alert)."""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

import src.trading.notify_digest as nd
from src.trading.holding_signals import HoldingSignalResult, SignalEvent
from src.trading.review import AggregateStats


def trading_doc(candidates: list[dict[str, Any]], regime: str = 'neutral') -> dict[str, Any]:
    return {'environment': {'regime': regime}, 'candidates': candidates}


CAND = {
    'code': '600519',
    'name': '贵州茅台',
    'state': 'in_buy_zone',
    'buy_zone_low': 1710.0,
    'buy_zone_high': 1795.5,
    'stop': 1573.2,
    'limit_up_unexecutable': False,
}

AS_OF = date(2026, 8, 20)


# ---------- build_daily_message ----------

def test_daily_message_watch_to_buy_zone() -> None:
    msg = nd.build_daily_message(trading_doc([CAND]), {'600519': 'watch'}, AS_OF)
    assert msg is not None
    title, desp = msg
    assert '1 只进入买区' in title and '贵州茅台' in desp
    assert '已进入买区 [1710.00 - 1795.50]，止损参考 1573.20' in desp
    assert '环境档位：中性' in desp


def test_daily_message_none_when_no_transition() -> None:
    # 无候选 / 昨日非 watch / 今日非 in_buy_zone -> 均不推
    assert nd.build_daily_message(trading_doc([]), {}, AS_OF) is None
    assert nd.build_daily_message(trading_doc([CAND]), {'600519': 'in_buy_zone'}, AS_OF) is None
    assert nd.build_daily_message(trading_doc([CAND]), {}, AS_OF) is None  # 昨日无记录不轰炸
    near = {**CAND, 'state': 'near_buy_zone'}
    assert nd.build_daily_message(trading_doc([near]), {'600519': 'watch'}, AS_OF) is None


def test_daily_message_limit_up_annotation() -> None:
    cand = {**CAND, 'limit_up_unexecutable': True}
    msg = nd.build_daily_message(trading_doc([cand]), {'600519': 'watch'}, AS_OF)
    assert msg is not None
    assert '（当日一字涨停，无法买入）' in msg[1]


def test_daily_message_missing_prices_dash() -> None:
    cand = {**CAND, 'buy_zone_low': None, 'buy_zone_high': None, 'stop': None}
    msg = nd.build_daily_message(trading_doc([cand]), {'600519': 'watch'}, AS_OF)
    assert msg is not None
    assert '已进入买区 [— - —]，止损参考 —' in msg[1]


def test_daily_message_multiple_and_regime_label() -> None:
    other = {**CAND, 'code': '000001', 'name': '平安银行'}
    msg = nd.build_daily_message(
        trading_doc([CAND, other], regime='offense'),
        {'600519': 'watch', '000001': 'watch'},
        AS_OF,
    )
    assert msg is not None
    assert '2 只进入买区' in msg[0]
    assert '环境档位：进攻' in msg[1]


# ---------- build_weekly_message ----------

def hold(health: str = 'holding', profit: float | None = 1.2) -> HoldingSignalResult:
    return HoldingSignalResult(
        code='600519', name='测试股', health=health, close=10.0,
        profit_pct=profit, suggested_stop=None,
        events=[] if health == 'holding' else [SignalEvent('break_ma50', '收盘跌破 50 日均线')],
    )


def stats(n: int = 0, win_rate: float | None = None) -> AggregateStats:
    return AggregateStats(
        n=n, win_rate=win_rate, avg_r=None if n == 0 else 0.5,
        profit_factor=None if n == 0 else 1.5, expectancy=None if n == 0 else 100.0,
        max_drawdown=None if n == 0 else 50.0,
        by_regime={'neutral': {'n': n, 'win_rate': win_rate}} if n else {},
    )


def test_weekly_message_no_trades() -> None:
    title, desp = nd.build_weekly_message(trading_doc([]), stats(), [], AS_OF)
    assert '交易周报' in title
    assert '本周无已完成交易' in desp
    assert '无持仓' in desp


def test_weekly_message_with_stats_and_holdings() -> None:
    s = stats(n=4, win_rate=0.75)
    _, desp = nd.build_weekly_message(trading_doc([]), s, [hold('warning')], AS_OF)
    assert '已完成 4 笔，胜率 75%' in desp
    assert '平均 R +0.50，盈亏比 1.50，期望 +100 元' in desp
    assert '最大回撤 50 元' in desp
    assert '中性期入场：4 笔，胜率 75%' in desp
    assert '浮盈 +1.2%，有事件' in desp
    assert '收盘跌破 50 日均线' in desp


def test_weekly_message_frozen_and_null_profit() -> None:
    _, desp = nd.build_weekly_message(trading_doc([]), stats(), [hold('frozen', None)], AS_OF)
    assert '浮盈 —' in desp and '冻结' in desp


def test_weekly_message_no_drawdown_line_when_zero() -> None:
    s = AggregateStats(n=2, win_rate=1.0, avg_r=1.0, profit_factor=None, expectancy=50.0, max_drawdown=0.0, by_regime={})
    _, desp = nd.build_weekly_message(trading_doc([]), s, [], AS_OF)
    assert '最大回撤' not in desp
    assert '盈亏比 ∞' in desp


# ---------- push (mock send_alert) ----------

def test_push_daily_sends_only_on_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(nd, 'send_alert', lambda t, d: sent.append((t, d)) or True)
    assert nd.push_daily(trading_doc([]), {}, AS_OF) is False  # 无迁移不发
    assert sent == []
    assert nd.push_daily(trading_doc([CAND]), {'600519': 'watch'}, AS_OF) is True
    assert len(sent) == 1


def test_push_weekly(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(nd, 'send_alert', lambda t, d: sent.append((t, d)) or True)
    assert nd.push_weekly(trading_doc([]), stats(), [], AS_OF) is True
    assert '交易周报' in sent[0][0]
