"""龙头规则边界与组合"""
from src.scoring.leader_rule import classify_leader


def test_three_star_strength_90_rsi_in_band():
    """strength >= 90 且 RSI ∈ [50, 70] → ⭐⭐⭐"""
    assert classify_leader(90, 50.0) == '⭐⭐⭐'
    assert classify_leader(95, 65.0) == '⭐⭐⭐'
    assert classify_leader(99, 70.0) == '⭐⭐⭐'


def test_strength_90_but_rsi_overbought_degrades_to_one():
    """strength 90 但 RSI > 70（超买）→ 不入 ⭐⭐⭐ / ⭐⭐，仅 ⭐"""
    assert classify_leader(90, 71.0) == '⭐'
    assert classify_leader(95, 80.0) == '⭐'


def test_two_star_strength_80_rsi_in_extended_band():
    """strength ∈ [80, 89] 且 RSI ∈ [45, 70] → ⭐⭐"""
    assert classify_leader(80, 45.0) == '⭐⭐'
    assert classify_leader(85, 60.0) == '⭐⭐'
    assert classify_leader(89, 70.0) == '⭐⭐'


def test_one_star_strength_70_plus_rsi_outside_band():
    """strength ≥ 70 但 RSI 不在范围内 → ⭐"""
    assert classify_leader(85, 40.0) == '⭐'
    assert classify_leader(70, 50.0) == '⭐'
    assert classify_leader(79, 75.0) == '⭐'


def test_no_label_strength_below_70():
    """strength < 70 → 空字符串"""
    assert classify_leader(69, 60.0) == ''
    assert classify_leader(50, 50.0) == ''
    assert classify_leader(0, 30.0) == ''


def test_strength_none_returns_empty():
    """strength_60d 缺失 → 空（无法判定）"""
    assert classify_leader(None, 60.0) == ''
    assert classify_leader(None, None) == ''


def test_rsi_none_falls_back_to_strength_only():
    """RSI 缺失时仅看 strength：≥ 70 给 ⭐，否则空"""
    assert classify_leader(90, None) == '⭐'
    assert classify_leader(70, None) == '⭐'
    assert classify_leader(69, None) == ''


def test_boundary_strength_exact_80_rsi_70():
    """边界值：strength=80 RSI=70 → ⭐⭐（80≥80 且 45≤70≤70）"""
    assert classify_leader(80, 70.0) == '⭐⭐'


def test_boundary_strength_exact_90_rsi_50():
    """边界值：strength=90 RSI=50 → ⭐⭐⭐"""
    assert classify_leader(90, 50.0) == '⭐⭐⭐'
