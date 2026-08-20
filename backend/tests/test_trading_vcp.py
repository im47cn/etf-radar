"""vcp.py 单测: zigzag / VCP 各门槛 / 关键价位 / 状态机三态 / 一字板 (spec §1.4-§1.6)."""
from __future__ import annotations

import numpy as np

from src.trading.vcp import classify_state, find_vcp, is_one_word_limit_up, zigzag
from tests.test_trading_fixtures import legs_series, volumes

LEGS3 = [(100.0, 75.0), (93.0, 79.0), (86.0, 80.0)]  # 深度 25% -> 15.1% -> 7%


def test_zigzag_alternating_pivots() -> None:
    pivots = zigzag(np.array([100.0, 96.0, 104.0, 98.0, 103.0]))
    assert [(p.kind, p.price) for p in pivots] == [('H', 100.0), ('L', 96.0), ('H', 104.0), ('L', 98.0), ('H', 103.0)]


def test_zigzag_below_threshold_no_pivot() -> None:
    """反向波动 <4% 不确认转向: 单 pivot (进行中极值)。"""
    pivots = zigzag(np.array([100.0, 99.0, 100.5]))
    assert len(pivots) == 1
    assert pivots[0].kind == 'H'


def test_vcp_three_contractions_full_fields() -> None:
    """主形态: 3 段收缩, pivot=100, 止损取 pivot*0.92 (92 > 最后 swing low 80), 近买区。"""
    cs = legs_series(LEGS3, tail_to=98.0)
    r = find_vcp(np.array(cs), volumes(len(cs)))
    assert r is not None
    assert r.contractions == 3
    np.testing.assert_allclose(r.depths, [0.25, 0.1505, 0.0698], atol=1e-3)
    assert r.depth_pct == 0.25  # (100-75)/100
    assert 0.0 <= r.quality <= 1.0
    assert r.volume_dryup is True
    assert r.pivot == 100.0
    assert r.buy_zone_low == 100.0
    assert r.buy_zone_high == 105.0  # pivot x1.05
    assert r.stop == 92.0  # max(80, 100*0.92) -> pivot 下限生效
    assert r.state == 'near_buy_zone'  # 98 = 0.98 x pivot


def test_vcp_stop_structural_wins_when_higher() -> None:
    """最后 swing low (93) > pivot*0.92 (92) -> 结构位止损生效。"""
    cs = legs_series([(100.0, 80.0), (98.0, 93.0)], tail_to=97.5)
    r = find_vcp(np.array(cs), volumes(len(cs)))
    assert r is not None
    assert r.contractions == 2
    assert r.stop == 93.0


def test_vcp_state_in_buy_zone_on_breakout() -> None:
    """末端收盘 102 ∈ [100, 105] -> in_buy_zone (pivot 取结构高点, 不随末端突破漂移)。"""
    cs = legs_series(LEGS3, tail_to=102.0)
    r = find_vcp(np.array(cs), volumes(len(cs)))
    assert r is not None
    assert r.pivot == 100.0
    assert r.state == 'in_buy_zone'


def test_vcp_state_watch_below_near_zone() -> None:
    cs = legs_series(LEGS3, tail_to=91.0)  # 0.91 x pivot < 0.97
    r = find_vcp(np.array(cs), volumes(len(cs)))
    assert r is not None
    assert r.state == 'watch'


def test_vcp_reject_depth_not_decaying() -> None:
    """第二段深度 17% > 20% x 0.8 = 16% -> 非单调递减, 拒。"""
    cs = legs_series([(100.0, 80.0), (98.8, 82.0)], tail_to=90.0)
    assert find_vcp(np.array(cs), volumes(len(cs))) is None


def test_vcp_reject_single_contraction() -> None:
    cs = legs_series([(100.0, 75.0)], tail_to=91.0)
    assert find_vcp(np.array(cs), volumes(len(cs))) is None


def test_vcp_reject_base_too_deep() -> None:
    """基部总深 (100-60)/100 = 40% > 35%, 拒 (单段深度无独立上限, 由总深门槛拦)。"""
    cs = legs_series([(100.0, 60.0), (66.0, 63.0)], tail_to=70.0)
    assert find_vcp(np.array(cs), volumes(len(cs))) is None


def test_vcp_reject_no_volume_dryup() -> None:
    cs = legs_series([(100.0, 75.0), (93.0, 79.0)], tail_to=97.5)
    assert find_vcp(np.array(cs), np.full(len(cs), 1e6)) is None


def test_vcp_empty_window() -> None:
    assert find_vcp(np.array([]), np.array([])) is None


def test_classify_state_three_states() -> None:
    assert classify_state(102.0, 100.0) == 'in_buy_zone'  # 区间内
    assert classify_state(100.0, 100.0) == 'in_buy_zone'  # 下沿 (突破日收盘)
    assert classify_state(105.0, 100.0) == 'in_buy_zone'  # 上沿
    assert classify_state(106.0, 100.0) == 'watch'  # 超买区上方 (已跑远)
    assert classify_state(97.0, 100.0) == 'near_buy_zone'  # 距下沿恰 3%
    assert classify_state(96.9, 100.0) == 'watch'
    assert classify_state(50.0, 100.0) == 'watch'
    assert classify_state(50.0, 0.0) == 'watch'  # 非法 pivot 护栏


def test_is_one_word_limit_up() -> None:
    assert is_one_word_limit_up(10.0, 10.0, 10.0, 10.0, 9.1) is True  # 一字 + 9.9% 涨幅
    assert is_one_word_limit_up(10.0, 10.0, 10.0, 10.0, 9.5) is False  # 涨幅不足 9.5%
    assert is_one_word_limit_up(9.5, 10.0, 9.4, 10.0, 9.1) is False  # 非一字 (有振幅)
    assert is_one_word_limit_up(10.0, 10.0, 10.0, 10.0, 0.0) is False  # 无昨收


def test_vcp_volume_guards() -> None:
    """量能护栏: volume 空 / 全零 / 末端 50 日均量为零 -> None。"""
    cs = np.array(legs_series([(100.0, 75.0), (93.0, 79.0)], tail_to=97.5))
    assert find_vcp(cs, np.array([])) is None  # volume 序列为空
    assert find_vcp(cs, np.zeros(len(cs))) is None  # 全零量能
    v = np.array([1e6] * 10 + [0.0] * 50)  # 窗均量>0 但 v50=0 (volume 与 close 长度独立)
    assert find_vcp(cs, v) is None
