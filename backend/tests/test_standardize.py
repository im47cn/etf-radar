import pandas as pd  # type: ignore[import-untyped]
from src.etl.standardize import standardize_ohlc, STANDARD_COLUMNS


def test_standardize_adds_missing_amount_as_nan() -> None:
    df = pd.DataFrame({
        'Date': pd.to_datetime(['2026-06-04', '2026-06-05']),
        'Open': [100, 101], 'High': [102, 103], 'Low': [99, 100],
        'Close': [101, 102], 'Volume': [1000, 2000],
    })
    out = standardize_ohlc(df, source='yfinance')
    assert set(STANDARD_COLUMNS).issubset(set(out.columns))
    assert out['amount'].isna().all()
    assert str(out['date'].dt.tz) == 'UTC'


def test_standardize_akshare_keeps_amount() -> None:
    df = pd.DataFrame({
        '日期': pd.to_datetime(['2026-06-04']),
        '开盘': [1.0], '最高': [1.1], '最低': [0.9],
        '收盘': [1.05], '成交量': [10000], '成交额': [10500.0],
    })
    out = standardize_ohlc(df, source='akshare')
    assert out['amount'].iloc[0] == 10500.0
