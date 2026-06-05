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


@patch('src.providers.yfinance_provider.time.sleep')
@patch('src.providers.yfinance_provider.yf.Ticker')
def test_retries_then_succeeds(mock_ticker: MagicMock, mock_sleep: MagicMock) -> None:
    good_df = pd.DataFrame({
        'Open': [100], 'High': [101], 'Low': [99], 'Close': [100], 'Volume': [1000],
    }, index=pd.to_datetime(['2026-06-04'], utc=True))
    good_df.index.name = 'Date'
    # 前两次抛异常, 第三次成功
    mock_ticker.return_value.history.side_effect = [
        Exception('timeout'), Exception('timeout'), good_df,
    ]
    p = YfinanceProvider(max_retries=3, base_delay=2.0)
    df = p.fetch_ohlc('SOXX', 5)
    assert not df.empty
    assert mock_sleep.call_count == 2  # 前两次失败后各 sleep 一次, 第三次成功不 sleep
    mock_sleep.assert_any_call(2.0)   # attempt 0: 2.0 * 2^0
    mock_sleep.assert_any_call(4.0)   # attempt 1: 2.0 * 2^1


@patch('src.providers.yfinance_provider.time.sleep')
@patch('src.providers.yfinance_provider.yf.Ticker')
def test_all_retries_exhausted_raises_provider_error(
    mock_ticker: MagicMock, mock_sleep: MagicMock,
) -> None:
    from src.providers.base import ProviderError
    mock_ticker.return_value.history.side_effect = ConnectionError('network fail')
    p = YfinanceProvider(max_retries=3, base_delay=0.01)
    with pytest.raises(ProviderError, match='network fail'):
        p.fetch_ohlc('SOXX', 5)
    assert mock_ticker.return_value.history.call_count == 3


@patch('src.providers.yfinance_provider.time.sleep')
@patch('src.providers.yfinance_provider.yf.Ticker')
def test_empty_data_not_retried(mock_ticker: MagicMock, mock_sleep: MagicMock) -> None:
    mock_ticker.return_value.history.return_value = pd.DataFrame()
    p = YfinanceProvider(max_retries=3)
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('NONEXIST', 5)
    # history 只应被调用一次, 不重试
    assert mock_ticker.return_value.history.call_count == 1
    assert mock_sleep.call_count == 0


@patch('src.providers.yfinance_provider.yf.Ticker')
def test_auto_adjust_true_passed(mock_ticker: MagicMock) -> None:
    """确保调用 yfinance 时使用 auto_adjust=True (Task 1.4 契约)"""
    mock_ticker.return_value.history.return_value = pd.DataFrame()
    p = YfinanceProvider()
    try:
        p.fetch_ohlc('SOXX', 7)
    except EmptyDataError:
        pass
    mock_ticker.return_value.history.assert_called_once_with(period='7d', auto_adjust=True)
