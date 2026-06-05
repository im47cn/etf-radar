import pandas as pd  # type: ignore[import-untyped]
import pytest
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


def test_standardize_yfinance_with_datetime_index() -> None:
    # 真实 yfinance 输出格式: DatetimeIndex(name='Date'), 故意反序输入
    idx = pd.DatetimeIndex(['2026-06-05', '2026-06-04'], name='Date')
    df = pd.DataFrame({
        'Open': [101.0, 100.0], 'High': [103.0, 102.0], 'Low': [100.0, 99.0],
        'Close': [102.0, 101.0], 'Volume': [2000, 1000],
    }, index=idx)
    out = standardize_ohlc(df, source='yfinance')
    assert list(out.columns) == STANDARD_COLUMNS
    assert str(out['date'].dt.tz) == 'UTC'
    assert out['date'].iloc[0] < out['date'].iloc[1]  # 反序输入 → sort_values 应正排
    assert out['close'].iloc[0] == 101.0  # 验证早一天的值在前


def test_standardize_yfinance_drops_adj_close_if_present() -> None:
    # 验证 'Adj Close' 列存在时不会引发列碰撞
    df = pd.DataFrame({
        'Date': pd.to_datetime(['2026-06-04']),
        'Open': [100.0], 'High': [102.0], 'Low': [99.0],
        'Close': [101.0], 'Adj Close': [101.0], 'Volume': [1000],
    })
    out = standardize_ohlc(df, source='yfinance')
    # 'Adj Close' 不在 YFINANCE_MAP 中, 会被 df[STANDARD_COLUMNS] 自然丢弃
    assert list(out.columns) == STANDARD_COLUMNS
    assert out['close'].iloc[0] == 101.0


def test_standardize_invalid_source_raises() -> None:
    with pytest.raises(ValueError, match='unknown source'):
        standardize_ohlc(pd.DataFrame(), source='bloomberg')  # type: ignore[arg-type]
