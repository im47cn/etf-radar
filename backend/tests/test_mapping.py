import pandas as pd  # type: ignore[import-untyped]
from src.scoring.mapping import mapping_score, _align_log_returns


def _df(dates: object, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({'date': pd.to_datetime(dates, utc=True), 'close': closes})


def test_align_intersects_dates() -> None:
    us = _df(['2026-06-01', '2026-06-02', '2026-06-03'], [100.0, 101.0, 102.0])
    cn = _df(['2026-06-02', '2026-06-03'], [10.0, 11.0])
    aligned = _align_log_returns(us, cn)
    # 第 1 个对齐日是 06-03 (log_ret 需要前一日, 所以 us 从 06-02 开始有 log_ret, cn 从 06-03 开始)
    assert len(aligned) == 1


def test_mapping_perfect_corr() -> None:
    us = _df(pd.date_range('2026-01-01', periods=80, tz='UTC'),
             [100.0 + i * 0.5 for i in range(80)])
    cn = _df(pd.date_range('2026-01-01', periods=80, tz='UTC'),
             [10.0 + i * 0.05 for i in range(80)])  # 完美线性同向
    score = mapping_score(us, cn, window=60, min_aligned=30)
    assert score is not None
    assert score >= 95


def test_mapping_insufficient_data_returns_none() -> None:
    us = _df(['2026-01-01'], [100.0])
    cn = _df(['2026-01-01'], [10.0])
    assert mapping_score(us, cn, window=60, min_aligned=30) is None


def test_mapping_negative_corr_absolute() -> None:
    """反向走势也是 |corr| × 100"""
    us = _df(pd.date_range('2026-01-01', periods=80, tz='UTC'),
             [100.0 + i * 0.5 for i in range(80)])
    cn = _df(pd.date_range('2026-01-01', periods=80, tz='UTC'),
             [50.0 - i * 0.05 for i in range(80)])  # 完美反向
    score = mapping_score(us, cn, window=60, min_aligned=30)
    assert score is not None
    assert score >= 95  # abs(-1) × 100 = 100
