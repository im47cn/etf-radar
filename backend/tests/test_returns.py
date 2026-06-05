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


def test_returns_ytd_from_year_start() -> None:
    # 251 个交易日 - YTD 从年初首日算
    closes = [100.0] + [110.0] * 250
    df = _series(closes)
    r = compute_returns(df)
    assert r.r_ytd is not None
    # 251 个 trading days 跨过年, 取 last close / first close 同年
    # 由于 date_range 起点 2025-01-01, 250 个之后是 2025-09-08 仍在同年
    assert r.r_ytd == pytest.approx(math.log(110 / 100))
