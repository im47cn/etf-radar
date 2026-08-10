"""stats_utils 纯函数测试: 已知值 + 无前视 + ARCH 检出."""
from __future__ import annotations

import numpy as np

from src.evidence.stats_utils import (
    acf,
    arch_per_theme,
    forward_cum,
    ic_by_horizon,
    ljung_box,
    rolling_ic_multi,
)


def test_acf_linear_trend_high_autocorrelation():
    x = np.arange(20, dtype=float)
    a = acf(x, 3)
    assert a[0] == 1.0
    assert a[1] > 0.5


def test_ljung_box_white_noise_not_significant():
    rng = np.random.default_rng(42)
    _, p = ljung_box(rng.normal(size=200), 10)
    assert p > 0.05


def test_ljung_box_autocorrelated_significant():
    rng = np.random.default_rng(0)
    x = np.zeros(200)
    for i in range(1, 200):
        x[i] = 0.8 * x[i - 1] + rng.normal()
    _, p = ljung_box(x, 10)
    assert p < 0.01


def test_ljung_box_strong_arch_no_underflow():
    # 强 ARCH (r² 高度自相关) 使 q 落到 cdf 饱和区 (~386, m=15);
    # 旧实现 1-cdf 会下溢为 0.0, sf 须给有限正值 (此例 ~1e-72)
    rng = np.random.default_rng(2)
    x = np.zeros(600)
    for i in range(1, 600):
        x[i] = 0.8 * x[i - 1] + rng.normal(scale=0.1)
    _, p = ljung_box(x ** 2, 15)
    assert 0.0 < p < 0.01  # 不会下溢成 0.0, 仍判定显著


def test_forward_cum_no_lookahead_and_tail_nan():
    r = np.array([[1.0], [2.0], [3.0], [4.0]])
    f = forward_cum(r, 2)
    assert f[0, 0] == 5.0  # r[1]+r[2], 不含 t 及之前
    assert f[1, 0] == 7.0  # r[2]+r[3]
    assert np.isnan(f[2, 0])  # 末端无前瞻
    assert np.isnan(f[3, 0])


def test_ic_by_horizon_perfect_positive_correlation():
    # strength 每日同排名, returns 每日同序 → forward 累计同序 → IC≈1
    T, N = 30, 10
    rank = np.arange(N, dtype=float)
    strength = np.tile(rank, (T, 1))
    returns = np.tile(rank, (T, 1)) * 0.01
    out = ic_by_horizon(strength, returns, horizons=(1, 5))
    assert out[0]["horizon"] == 1
    assert out[0]["ic"] > 0.99
    assert out[0]["n"] > 0
    # 新字段: 全样本范围 + 最近实际
    assert out[0]["ic_min"] is not None and out[0]["ic_max"] is not None
    assert out[0]["ic_min"] <= out[0]["ic"] <= out[0]["ic_max"]
    assert out[0]["recent_ic"] is not None


def test_rolling_ic_multi_respects_windows_and_no_lookahead():
    T, N = 80, 10
    rng = np.random.default_rng(1)
    strength = rng.normal(size=(T, N))
    returns = rng.normal(size=(T, N)) * 0.01
    dates = [f"2021-01-{i + 1:02d}" for i in range(T)]
    windows, horizon = (5, 20, 60), 20
    out = rolling_ic_multi(strength, returns, dates, windows=windows, horizon=horizon)
    assert len(out) > 0
    # 三档字段齐全
    assert all({"ic_5", "ic_20", "ic_60"} <= set(e) for e in out)
    # 末端 date 不超 T-horizon-1 (防前视)
    assert all(e["date"] <= dates[T - horizon - 1] for e in out)


def test_arch_per_theme_detects_volatility_clustering():
    rng = np.random.default_rng(0)
    T = 300
    arch = np.concatenate([
        rng.normal(scale=0.01, size=T // 2),   # 低波动块
        rng.normal(scale=0.5, size=T - T // 2),  # 高波动块 -> r² 强自相关
    ])
    white = rng.normal(scale=0.1, size=T)
    returns = np.column_stack([arch, white])
    out = arch_per_theme(returns, ["arch_theme", "white_theme"], m=10)
    by_id = {e["theme_id"]: e for e in out}
    assert by_id["arch_theme"]["is_arch"] is True
    assert by_id["white_theme"]["is_arch"] is False
