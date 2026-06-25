"""RSI(14) 与 量比 计算"""


from src.scoring.stock_indicators import compute_rsi, compute_volume_ratio


def test_rsi_insufficient_data_returns_none():
    """少于 15 个有效收盘价 → None"""
    closes = [10.0] * 14
    assert compute_rsi(closes) is None


def test_rsi_constant_prices_returns_50_or_nan():
    """价格全相等时 ta 库的 RSI 行为：可能返回 NaN（无变化）、50 或 100"""
    closes = [10.0] * 30
    result = compute_rsi(closes)
    assert result is None or result == 50.0 or result == 100.0


def test_rsi_strict_uptrend_near_100():
    """严格单调上涨 30 日 → RSI 应接近 100"""
    closes = [10.0 + i * 0.5 for i in range(30)]
    rsi = compute_rsi(closes)
    assert rsi is not None and rsi > 95.0


def test_rsi_strict_downtrend_near_0():
    """严格单调下跌 → RSI 应接近 0"""
    closes = [30.0 - i * 0.5 for i in range(30)]
    rsi = compute_rsi(closes)
    assert rsi is not None and rsi < 5.0


def test_rsi_skips_none_values():
    """收盘价含 None（停牌）→ dropna 后用剩余"""
    closes = [10.0 + i * 0.5 if i % 5 != 0 else None for i in range(40)]
    rsi = compute_rsi(closes)
    assert rsi is not None
    assert 0 <= rsi <= 100


def test_volume_ratio_standard():
    """今日量 / 前 5 日均量"""
    volumes = [100, 100, 100, 100, 100, 200]
    assert compute_volume_ratio(volumes) == 2.0


def test_volume_ratio_with_today_none_returns_none():
    volumes = [100, 100, 100, 100, 100, None]
    assert compute_volume_ratio(volumes) is None


def test_volume_ratio_insufficient_prev_returns_none():
    """前 5 日有效量不足 5 个"""
    volumes = [100, None, None, 100, 100, 200]
    assert compute_volume_ratio(volumes) is None


def test_volume_ratio_zero_mean_returns_none():
    """前 5 日均量为 0（极端停牌）"""
    volumes = [0, 0, 0, 0, 0, 100]
    assert compute_volume_ratio(volumes) is None


def test_volume_ratio_length_lt_6_returns_none():
    assert compute_volume_ratio([100, 200, 300]) is None
