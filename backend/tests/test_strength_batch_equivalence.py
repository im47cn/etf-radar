"""batch_strength_per_dim 与 strength_per_dim 逐元素等价（round 后 ±1 误差容忍）"""

import numpy as np

from src.scoring.strength import batch_strength_per_dim, strength_per_dim


def test_batch_matches_single_no_nan():
    rng = np.random.default_rng(42)
    returns = rng.uniform(-0.5, 0.5, size=1000)
    batch_out = batch_strength_per_dim(returns.copy(), k=2.0, days_in_dim=60)
    for i, r in enumerate(returns):
        single = strength_per_dim(r, returns.tolist(), k=2.0, days_in_dim=60)
        assert abs(int(batch_out[i]) - single) <= 1, f'mismatch at {i}'


def test_batch_propagates_nan():
    arr = np.array([0.1, np.nan, 0.2, np.nan, 0.3])
    out = batch_strength_per_dim(arr, k=2.0, days_in_dim=60)
    assert np.isnan(out[1])
    assert np.isnan(out[3])
    assert not np.isnan(out[0])


def test_batch_all_nan_returns_all_nan():
    arr = np.array([np.nan, np.nan, np.nan])
    out = batch_strength_per_dim(arr, k=2.0, days_in_dim=60)
    assert np.all(np.isnan(out))


def test_batch_empty_array():
    out = batch_strength_per_dim(np.array([]), k=2.0, days_in_dim=60)
    assert len(out) == 0


def test_batch_all_equal_returns_same_score():
    """所有元素相等时百分位应为 50（average rank），M 也相同 → score 相同"""
    arr = np.full(100, 0.1)
    out = batch_strength_per_dim(arr, k=2.0, days_in_dim=60)
    assert len(set(out.tolist())) == 1


def test_batch_score_range_0_to_99():
    rng = np.random.default_rng(0)
    arr = rng.uniform(-2.0, 2.0, size=500)
    out = batch_strength_per_dim(arr, k=2.0, days_in_dim=60)
    valid = out[~np.isnan(out)]
    assert valid.min() >= 0
    assert valid.max() <= 99
