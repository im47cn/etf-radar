"""review 单测 — round trip 切分 (M3 规则一致) + 纪律四维 + 结果分 + 聚合 (spec §2.5)."""
from __future__ import annotations

import copy
from typing import Any

from src.trading.review import (
    ReviewContext,
    aggregate_stats,
    review_round_trip,
    split_round_trips,
)

_SEQ = [0]


def ev(
    side: str,
    day: str,
    price: float,
    shares: int,
    stop: float | None = None,
    code: str = '600519',
    name: str = '测试股',
) -> dict[str, Any]:
    """构造 trades 事件行 (created_at 单调递增, 保证同日排序稳定)。"""
    _SEQ[0] += 1
    return {
        'id': f'00000000-0000-0000-0000-{_SEQ[0]:012d}',
        'user_id': 'u1',
        'code': code,
        'name': name,
        'side': side,
        'trade_date': day,
        'price': price,
        'shares': shares,
        'stop_after': stop,
        'reason': None,
        'created_at': f'2026-01-01T00:00:{_SEQ[0]:02d}Z',
    }


def mk_ctx(**over: Any) -> ReviewContext:
    base: dict[str, Any] = {
        'buy_zone': (9.5, 10.5),
        'holding_days': ['08-01', '08-02', '08-03', '08-04', '08-05'],
        'closes': [10.0, 10.0, 10.0, 10.0, 10.0],
        'lows': [9.8, 9.8, 9.8, 9.8, 9.8],
        'stop_levels': [9.0, 9.0, 9.0, 9.0, 9.0],
        'signal_event_dates': [],
        'equity': None,
        'risk_per_trade_pct': 0.75,
        'max_position_pct': 20.0,
    }
    base.update(over)
    return ReviewContext(**base)


def mk_trip(trades: list[dict[str, Any]]) -> list[Any]:
    return split_round_trips(copy.deepcopy(trades))


# ---------- split_round_trips (M3 derivePositions 规则一致) ----------

def test_simple_open_close() -> None:
    trips = mk_trip([ev('open', '08-01', 10.0, 100, stop=9.0), ev('close', '08-05', 11.0, 100)])
    assert len(trips) == 1
    t = trips[0]
    assert (t.open_date, t.open_price, t.open_shares, t.stop_at_open) == ('08-01', 10.0, 100, 9.0)
    assert (t.close_date, t.close_price) == ('08-05', 11.0)
    assert t.realized_pnl == 100.0  # 1100 - 1000


def test_add_updates_cost_and_pnl() -> None:
    trips = mk_trip(
        [
            ev('open', '08-01', 10.0, 100),
            ev('add', '08-02', 12.0, 100),
            ev('close', '08-05', 11.0, 200),
        ]
    )
    assert trips[0].realized_pnl == round(2200.0 - (1000.0 + 1200.0), 2)  # 0


def test_partial_reduce_then_close() -> None:
    trips = mk_trip(
        [
            ev('open', '08-01', 10.0, 100),
            ev('reduce', '08-03', 10.5, 40),
            ev('close', '08-05', 11.0, 60),
        ]
    )
    assert trips[0].realized_pnl == round(40 * 10.5 + 60 * 11.0 - 1000.0, 2)  # 100


def test_reduce_to_zero_counts_as_close() -> None:
    trips = mk_trip([ev('open', '08-01', 10.0, 100), ev('reduce', '08-03', 10.5, 150)])
    assert len(trips) == 1
    assert trips[0].close_date == '08-03'


def test_open_position_without_close_excluded() -> None:
    trips = mk_trip([ev('open', '08-01', 10.0, 100)])
    assert trips == []


def test_orphan_reduce_and_close_ignored() -> None:
    assert mk_trip([ev('reduce', '08-01', 10.0, 100), ev('close', '08-02', 10.0, 100)]) == []


def test_add_without_position_treated_as_open() -> None:
    trips = mk_trip([ev('add', '08-01', 10.0, 100, stop=9.0), ev('close', '08-03', 11.0, 100)])
    assert len(trips) == 1
    assert trips[0].stop_at_open == 9.0


def test_reopen_after_close_makes_new_trip() -> None:
    trips = mk_trip(
        [
            ev('open', '08-01', 10.0, 100),
            ev('close', '08-02', 11.0, 100),
            ev('open', '08-03', 12.0, 100),
            ev('close', '08-04', 11.5, 100),
        ]
    )
    assert len(trips) == 2
    assert trips[0].open_date == '08-01' and trips[1].open_date == '08-03'


def test_codes_split_independently() -> None:
    trips = mk_trip(
        [
            ev('open', '08-01', 10.0, 100, code='600519'),
            ev('open', '08-02', 20.0, 200, code='000001'),
            ev('close', '08-03', 11.0, 100, code='600519'),
            ev('close', '08-04', 22.0, 200, code='000001'),
        ]
    )
    assert {t.code for t in trips} == {'600519', '000001'}


# ---------- review_round_trip: 纪律四维 ----------

SIMPLE = [ev('open', '08-01', 10.0, 100, stop=9.0), ev('close', '08-05', 11.0, 100)]


def score_of(trades: list[dict[str, Any]], ctx: ReviewContext) -> Any:
    trips = split_round_trips(copy.deepcopy(trades))
    return review_round_trip(trips[0], ctx)


def test_perfect_discipline_100() -> None:
    r = score_of(SIMPLE, mk_ctx())
    assert r.discipline_score == 100
    assert all(r.dimensions.values())
    assert r.result_r == 1.0  # pnl 100 / 初始风险 (10-9)*100=100
    assert r.holding_days == 5
    assert r.mae_pct == -2.0  # (9.8-10)/10


def test_entry_outside_buy_zone_minus25() -> None:
    r = score_of(SIMPLE, mk_ctx(buy_zone=(9.0, 9.8)))
    assert r.dimensions['entry_in_buy_zone'] is False
    assert r.discipline_score == 75


def test_no_buy_zone_structure_minus25() -> None:
    r = score_of(SIMPLE, mk_ctx(buy_zone=None))
    assert r.dimensions['entry_in_buy_zone'] is False


def test_no_initial_stop_minus25() -> None:
    trades = [ev('open', '08-01', 10.0, 100), ev('close', '08-05', 11.0, 100)]
    r = score_of(trades, mk_ctx())
    assert r.dimensions['stop_discipline'] is False
    assert r.result_r is None  # 无初始风险锚点


def test_stop_triggered_exit_in_window_ok() -> None:
    # day2 (idx1) 收盘 8.5 < 止损 9.0 触发; 退出 idx4 距离 3 > 2 -> 违纪
    r = score_of(SIMPLE, mk_ctx(closes=[10.0, 8.5, 8.4, 8.4, 8.4]))
    assert r.dimensions['stop_discipline'] is False
    # 缩短响应: 持仓窗只到 idx3 (距离 2) -> 遵守
    r2 = score_of(
        [ev('open', '08-01', 10.0, 100, stop=9.0), ev('close', '08-04', 8.4, 100)],
        mk_ctx(
            holding_days=['08-01', '08-02', '08-03', '08-04'],
            closes=[10.0, 8.5, 8.4, 8.4],
            lows=[9.8, 8.5, 8.4, 8.4],
            stop_levels=[9.0, 9.0, 9.0, 9.0],
        ),
    )
    assert r2.dimensions['stop_discipline'] is True


def test_stop_level_none_days_skipped() -> None:
    # 入场日 stop_after 尚未记录 (None), 次日起 9.0; 触发判定跳过 None 日
    r = score_of(
        [ev('open', '08-01', 10.0, 100, stop=9.0), ev('close', '08-05', 11.0, 100)],
        mk_ctx(stop_levels=[None, 9.0, 9.0, 9.0, 9.0]),
    )
    assert r.dimensions['stop_discipline'] is True


def test_exit_responsiveness_window() -> None:
    # 信号事件在 idx1 (距退出 idx4 为 3 > 2) -> 违纪
    r = score_of(SIMPLE, mk_ctx(signal_event_dates=['08-02']))
    assert r.dimensions['exit_responsiveness'] is False
    # 信号事件在 idx3 (距退出 1 <= 2) -> 遵守
    r2 = score_of(SIMPLE, mk_ctx(signal_event_dates=['08-04']))
    assert r2.dimensions['exit_responsiveness'] is True


def test_no_signal_events_compliant() -> None:
    r = score_of(SIMPLE, mk_ctx())
    assert r.dimensions['exit_responsiveness'] is True


def test_position_compliance_equity_checks() -> None:
    # equity 100000: 市值 1000 <= 20% ✓; 风险额 100 <= 750 ✓
    r = score_of(SIMPLE, mk_ctx(equity=100000.0))
    assert r.dimensions['position_compliance'] is True
    # equity 1000: 市值 1000 > 200 (20%) -> 违纪
    r2 = score_of(SIMPLE, mk_ctx(equity=1000.0))
    assert r2.dimensions['position_compliance'] is False
    # equity 12800: 市值 ✓, 风险额 100 > 96*1.05=100.8 边界内; 12800*0.75%*1.05=100.8 -> 合规
    r3 = score_of(SIMPLE, mk_ctx(equity=12800.0))
    assert r3.dimensions['position_compliance'] is True
    # equity 100: 市值 1000 > 20 -> 且风险超 -> 违纪
    r4 = score_of(SIMPLE, mk_ctx(equity=100.0))
    assert r4.dimensions['position_compliance'] is False


def test_position_compliance_no_stop_only_cap() -> None:
    # 无止损 + equity 1000: 市值超限 -> 违纪 (仅查市值分支)
    trades = [ev('open', '08-01', 10.0, 100), ev('close', '08-05', 11.0, 100)]
    r = score_of(trades, mk_ctx(equity=1000.0))
    assert r.dimensions['position_compliance'] is False


def test_zero_initial_risk_r_is_none() -> None:
    # 止损 = 入场价 -> 初始风险 0 -> R 无定义
    trades = [ev('open', '08-01', 10.0, 100, stop=10.0), ev('close', '08-05', 11.0, 100)]
    r = score_of(trades, mk_ctx())
    assert r.result_r is None


def test_result_fields_reported() -> None:
    r = score_of(SIMPLE, mk_ctx())
    assert r.realized_pnl == 100.0
    assert r.open_date == '08-01' and r.close_date == '08-05'
    assert r.events['dimensions'] == r.dimensions


# ---------- aggregate_stats ----------

def _result(pnl: float, r: float | None, open_date: str, close_date: str) -> Any:
    trips = split_round_trips(
        [ev('open', open_date, 10.0, 100, stop=9.0), ev('close', close_date, 10.0 + pnl / 100, 100)]
    )
    res = review_round_trip(trips[0], mk_ctx())
    # 直接覆盖统计字段 (避免为不同 pnl 构造行情)
    return res.__class__(
        code=res.code, name=res.name, open_date=open_date, close_date=close_date,
        realized_pnl=pnl, discipline_score=res.discipline_score, dimensions=res.dimensions,
        result_r=r, holding_days=res.holding_days, mae_pct=res.mae_pct, events=res.events,
    )


def test_aggregate_empty() -> None:
    s = aggregate_stats([], None)
    assert s.n == 0
    assert s.win_rate is None and s.avg_r is None and s.max_drawdown is None


def test_aggregate_mixed() -> None:
    results = [
        _result(200.0, 2.0, '07-01', '07-10'),  # 胜
        _result(-100.0, -1.0, '07-02', '07-05'),  # 负
        _result(100.0, 1.0, '07-03', '07-20'),  # 胜
    ]
    s = aggregate_stats(results, None)
    assert s.n == 3
    assert s.win_rate == round(2 / 3, 4)
    assert s.avg_r == round((2.0 - 1.0 + 1.0) / 3, 3)
    assert s.profit_factor == round(300.0 / 100.0, 3)
    assert s.expectancy == round(200.0 / 3, 2)
    # 累计 pnl 序列 (按 close_date): -100, +100, +200 -> 峰 0 后谷 -100 -> mdd 100
    assert s.max_drawdown == 100.0


def test_aggregate_no_losses_pf_none() -> None:
    results = [_result(100.0, 1.0, '07-01', '07-05'), _result(50.0, 0.5, '07-02', '07-06')]
    s = aggregate_stats(results, None)
    assert s.profit_factor is None
    assert s.max_drawdown == 0.0


def test_aggregate_by_regime() -> None:
    results = [
        _result(100.0, 1.0, '07-01', '07-05'),
        _result(-50.0, -0.5, '07-02', '07-06'),
        _result(80.0, 0.8, '07-03', '07-07'),
    ]
    s = aggregate_stats(results, {'07-01': 'offense', '07-02': 'defense', '07-03': 'unknown-x'})
    assert set(s.by_regime) == {'offense', 'defense', 'unknown-x'}
    assert s.by_regime['offense']['n'] == 1 and s.by_regime['offense']['win_rate'] == 1.0
    assert s.by_regime['defense']['win_rate'] == 0.0
    # 无 regime 记录的日期归 unknown
    s2 = aggregate_stats(results, {})
    assert set(s2.by_regime) == {'unknown'}
