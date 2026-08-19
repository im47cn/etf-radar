"""metals 指标纯函数测试 — 口径锚定 gsr_timing_backtest 预注册回测."""
from __future__ import annotations

import numpy as np
import pytest

from src.metals.indicators import (
    change_over,
    daily_change,
    gold_silver_ratio,
    rolling_corr,
    rolling_percentile,
    simple_return,
)


class TestRollingPercentile:
    def test_burn_in_is_nan(self) -> None:
        out = rolling_percentile(np.arange(10.0), 3)
        assert np.isnan(out[:2]).all()
        assert not np.isnan(out[2:]).any()

    def test_ascending_series_ends_at_max(self) -> None:
        # 单调上升序列, 末点必是窗口最大 → 分位 1.0
        out = rolling_percentile(np.arange(100.0), 10)
        assert out[-1] == 1.0
        assert out[9] == 1.0

    def test_descending_series_ends_at_min(self) -> None:
        out = rolling_percentile(np.arange(100.0)[::-1], 10)
        assert out[-1] == pytest.approx(1 / 10)  # 含自身

    def test_window_respected(self) -> None:
        # 窗口外的旧高点不影响分位
        x = np.array([100.0] + [1.0] * 10)
        out = rolling_percentile(x, 5)
        assert out[-1] == 1.0  # 5 日窗内 1.0 是最大(且并列, 含自身计为 1)


class TestGoldSilverRatio:
    def test_ratio(self) -> None:
        r = gold_silver_ratio(np.array([200.0, 400.0]), np.array([20.0, 40.0]))
        assert r.tolist() == [10.0, 10.0]


class TestDailyChangeAndCorr:
    def test_daily_change(self) -> None:
        d = daily_change(np.array([1.0, 3.0, 6.0]))
        assert np.isnan(d[0])
        assert d[1:].tolist() == [2.0, 3.0]

    def test_perfect_correlation(self) -> None:
        # 日变化须非常数(否则零方差), 用随机游走构造
        rng = np.random.default_rng(7)
        a = np.cumsum(rng.normal(0, 1, 30))
        out = rolling_corr(a, 2.0 * a + 1.0, 20)
        assert np.isnan(out[20 - 1])  # 窗口含首个 nan 日变化
        assert out[-1] == pytest.approx(1.0)

    def test_inverse_correlation(self) -> None:
        rng = np.random.default_rng(7)
        a = np.cumsum(rng.normal(0, 1, 30))
        out = rolling_corr(a, -a, 20)
        assert out[-1] == pytest.approx(-1.0)

    def test_zero_variance_is_nan(self) -> None:
        a = np.arange(30.0)
        out = rolling_corr(a, np.ones(30), 20)
        assert np.isnan(out).all()


class TestReturns:
    def test_simple_return(self) -> None:
        assert simple_return(np.array([100.0, 110.0]), 1) == pytest.approx(0.1)

    def test_simple_return_insufficient(self) -> None:
        with pytest.raises(ValueError, match='needs'):
            simple_return(np.array([1.0, 2.0]), 5)

    def test_change_over(self) -> None:
        assert change_over(np.array([0.01, 0.015, 0.013]), 2) == pytest.approx(0.003)

    def test_change_over_insufficient(self) -> None:
        with pytest.raises(ValueError, match='needs'):
            change_over(np.array([1.0]), 1)
