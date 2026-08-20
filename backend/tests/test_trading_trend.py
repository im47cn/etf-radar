"""trend.py 单测: 8 条趋势模板逐条 + 四阶段状态机 (spec §2.1/§1.2)."""
from __future__ import annotations

import numpy as np

from src.trading.trend import classify_stage, compute_trend, sma
from tests.test_trading_fixtures import flat, geo


def _arr(xs: list[float]) -> np.ndarray:
    return np.array(xs, dtype=np.float64)


def test_sma_basic() -> None:
    out = sma(_arr([1.0, 2.0, 3.0, 4.0]), 2)
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [1.5, 2.5, 3.5])


def test_perfect_uptrend_all_eight_pass() -> None:
    """几何上涨 + RS 注入 -> 8/8 全过, Stage 2。"""
    c = _arr(geo(300, 10.0, 1.003))
    t = compute_trend(c * 1.001, c * 0.999, c, rs_pct=85.0)
    assert t is not None
    assert t.criteria == [True] * 8
    assert t.pass_count == 8
    assert t.stage == 2


def test_flat_breaks_six_criteria_and_stage1() -> None:
    """横盘: 条1/2/3/4/5/8 皆 False (均线相等/零斜率/无 30% 抬升), 条6/7 过; Stage 1 缠绕。"""
    c = _arr(flat(300, 50.0))
    t = compute_trend(c, c, c, rs_pct=85.0)
    assert t is not None
    assert t.criteria == [False, False, False, False, False, True, True, False]
    assert t.pass_count == 2
    assert t.stage == 1


def test_rs_none_fails_criteria7_only() -> None:
    c = _arr(geo(300, 10.0, 1.003))
    t = compute_trend(c * 1.001, c * 0.999, c, rs_pct=None)
    assert t is not None
    assert t.criteria[:6] == [True] * 6
    assert t.criteria[6] is False  # 指数场景: 无 RS 恒 False
    assert t.criteria[7] is True
    assert t.pass_count == 7


def test_rs_below_70_fails_criteria7() -> None:
    c = _arr(geo(300, 10.0, 1.003))
    t = compute_trend(c * 1.001, c * 0.999, c, rs_pct=69.9)
    assert t is not None
    assert t.criteria[6] is False


def test_decline_below_ma200_falling_is_stage4() -> None:
    """高位横盘 -> 低位横盘: 价 < 200MA 且 200MA 下行 -> Stage 4。"""
    c = _arr(flat(150, 80.0) + flat(150, 50.0))
    t = compute_trend(c, c, c, rs_pct=85.0)
    assert t is not None
    assert t.stage == 4


def test_pullback_below_ma50_is_stage3() -> None:
    """涨后失守 50MA 但守住 200MA 上方 (>8%): 非 2 (pass 5), 非缠绕, 非下行 -> Stage 3。"""
    rise = geo(280, 10.0, 1.004)
    c = _arr(rise + np.linspace(rise[-1], rise[-1] * 0.70, 15).tolist())
    t = compute_trend(c * 1.001, c * 0.999, c, rs_pct=None)
    assert t is not None
    assert t.pass_count == 5
    assert t.stage == 3


def test_short_series_returns_none() -> None:
    c = _arr(geo(200, 10.0, 1.003))  # < 250 bars (次新股)
    assert compute_trend(c, c, c, rs_pct=85.0) is None


def test_classify_stage_order_two_first() -> None:
    """模板 >=6 优先归 Stage 2, 即便同时满足缠绕条件。"""
    assert classify_stage(100.0, 100.0, 100.5, 6) == 2  # dist=0 缠绕但 pass>=6


def test_classify_stage_wrap_boundary() -> None:
    # dist = 8% 恰在缠绕界内, 且 20 日累计斜率 < 0.4% -> Stage 1
    assert classify_stage(108.0, 100.0, 100.1, 4) == 1
    # dist = 8% 但斜率超平界 -> 落 Stage 3
    assert classify_stage(108.0, 100.0, 101.0, 4) == 3


def test_classify_stage4_needs_falling_ma200() -> None:
    assert classify_stage(99.0, 100.0, 100.5, 3) == 4  # 价<200MA 且 200MA 下行
    assert classify_stage(99.0, 100.0, 99.5, 3) == 3  # 200MA 上行 -> 归 3 (其余)
    assert classify_stage(101.0, 100.0, 100.5, 3) == 3  # 价>200MA -> 3


def test_nonpositive_prices_guard() -> None:
    """qfq 异常/负价格护栏: 末值均线或现价非正 -> 不评定 (None)。"""
    c = -_arr(geo(300, 10.0, 1.003))
    assert compute_trend(c, c, c, rs_pct=85.0) is None
