import pytest
from src.scoring.strength import (
    sigmoid_momentum, percentile_rank, dim_aggregate_return,
    strength_per_dim, composite_strength,
)
from src.models import Returns


def test_sigmoid_zero_is_50() -> None:
    assert sigmoid_momentum(0.0, k=5.0, days_in_dim=40) == pytest.approx(50, abs=0.01)


def test_sigmoid_strong_positive_saturates() -> None:
    # 年化 +1260% → sigmoid 接近 100
    v = sigmoid_momentum(2.0, k=5.0, days_in_dim=40)
    assert v > 95


def test_percentile_rank_basic() -> None:
    assert percentile_rank(50, [10, 20, 30, 40, 50]) == 100
    assert percentile_rank(10, [10, 20, 30, 40, 50]) == pytest.approx(20.0, abs=0.5)


def test_dim_aggregate_short() -> None:
    r = Returns(r_1d=0.01, r_5d=0.05)
    assert dim_aggregate_return(r, 'short') == pytest.approx(0.03)


def test_dim_aggregate_returns_none_if_all_missing() -> None:
    r = Returns()
    assert dim_aggregate_return(r, 'short') is None


def test_strength_per_dim_returns_int_0_99() -> None:
    s = strength_per_dim(0.05, [0.0, 0.01, 0.02, 0.03, 0.05], k=5.0, days_in_dim=40)
    assert 0 <= s <= 99  # 实现上限是 99 (留 100 给完美样本)


def test_composite_weighted_avg() -> None:
    """文档样本 94 是错的, 实际 round(94.6) = 95 (与舍入模式无关, banker's rounding 仅在 .5 时触发)"""
    c = composite_strength(short=77, mid=99, long=99, w_short=0.2, w_mid=0.4, w_long=0.4)
    assert c == 95


def test_sigmoid_strong_negative_saturates() -> None:
    """负向年化 → sigmoid 接近 0"""
    v = sigmoid_momentum(-2.0, k=5.0, days_in_dim=40)
    assert v < 5


def test_dim_aggregate_single_period_available() -> None:
    """只有一个子周期数据时仍返回该值"""
    r = Returns(r_1d=0.05)  # r_5d 缺失
    assert dim_aggregate_return(r, 'short') == pytest.approx(0.05)


def test_strength_per_dim_empty_pool_raises() -> None:
    """空 pool 应抛 ValueError 而非崩溃"""
    with pytest.raises(ValueError, match="pool_dim_returns must not be empty"):
        strength_per_dim(0.05, [], k=5.0, days_in_dim=40)


def test_composite_strength_weights_must_sum_to_one() -> None:
    """权重和 ≠ 1.0 触发 AssertionError"""
    with pytest.raises(AssertionError, match="weights must sum to 1.0"):
        composite_strength(short=50, mid=50, long=50, w_short=0.3, w_mid=0.4, w_long=0.4)
