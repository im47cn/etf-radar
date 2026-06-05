import math

import pandas as pd  # type: ignore[import-untyped]
import pytest

from src.scoring.returns import compute_returns


def _series(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.date_range('2025-01-01', periods=len(closes), tz='UTC'),
        'close': closes,
    })


def test_returns_basic_1d() -> None:
    df = _series([100.0, 110.0])
    r = compute_returns(df)
    assert r.r_1d == pytest.approx(math.log(110 / 100))


def test_returns_with_insufficient_data() -> None:
    df = _series([100.0])
    r = compute_returns(df)
    assert r.r_1d is None
    assert r.r_5d is None


def test_returns_ytd_only_uses_current_year() -> None:
    """YTD 跨年时只统计当年 (2025) 的收益, 排除 2024 数据"""
    # 显式构造跨年日期: 2024 末 + 2025 初
    dates_2024 = pd.date_range('2024-12-01', '2024-12-31', tz='UTC')
    dates_2025 = pd.date_range('2025-01-01', '2025-01-02', tz='UTC')
    closes_2024 = [100.0] * len(dates_2024)
    closes_2025 = [150.0, 160.0]
    df = pd.DataFrame({
        'date': list(dates_2024) + list(dates_2025),
        'close': closes_2024 + closes_2025,
    })
    r = compute_returns(df)
    # YTD 应基于 2025 年首日 (150) 到末日 (160), 而非 2024 年首日 (100)
    assert r.r_ytd == pytest.approx(math.log(160 / 150))


def test_returns_r_60d_value() -> None:
    """显式验证 r_60d 计算正确 (防止参数顺序回归)"""
    # 61 个数据点: 第 0 个 100, 中间随机, 第 60 个 120
    closes = [100.0] + [105.0] * 59 + [120.0]
    df = _series(closes)
    r = compute_returns(df)
    # r_60d 应该是从 60 天前 (closes[0]=100) 到今天 (closes[60]=120)
    assert r.r_60d == pytest.approx(math.log(120 / 100))
