import pandas as pd  # type: ignore[import-untyped]
import pytest
from unittest.mock import patch, MagicMock
from src.providers.yfinance_provider import YfinanceProvider
from src.providers.base import EmptyDataError


@patch('src.providers.yfinance_provider.yf.Ticker')
def test_fetch_ohlc_success(mock_ticker: MagicMock) -> None:
    fake_df = pd.DataFrame({
        'Open': [100, 101], 'High': [102, 103], 'Low': [99, 100],
        'Close': [101, 102], 'Volume': [1000, 2000],
    }, index=pd.to_datetime(['2026-06-04', '2026-06-05'], utc=True))
    fake_df.index.name = 'Date'
    mock_ticker.return_value.history.return_value = fake_df

    p = YfinanceProvider()
    df = p.fetch_ohlc('SOXX', 5)
    assert not df.empty
    assert 'close' in df.columns


@patch('src.providers.yfinance_provider.yf.Ticker')
def test_fetch_ohlc_empty_raises(mock_ticker: MagicMock) -> None:
    mock_ticker.return_value.history.return_value = pd.DataFrame()
    p = YfinanceProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('NONEXIST', 5)
