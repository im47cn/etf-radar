import pandas as pd  # type: ignore[import-untyped]
import pytest
from unittest.mock import patch, MagicMock
from src.providers.akshare_provider import AkshareProvider
from src.providers.base import EmptyDataError, ProviderError


@patch('src.providers.akshare_provider.ak.fund_etf_hist_em')
def test_fetch_ohlc_success(mock_hist: MagicMock) -> None:
    fake = pd.DataFrame({
        '日期': pd.to_datetime(['2026-06-04']),
        '开盘': [1.0], '最高': [1.1], '最低': [0.9],
        '收盘': [1.05], '成交量': [10000], '成交额': [10500.0],
    })
    mock_hist.return_value = fake
    p = AkshareProvider()
    df = p.fetch_ohlc('512480', 5)
    assert not df.empty
    assert df['amount'].iloc[0] == 10500.0


@patch('src.providers.akshare_provider.ak.fund_etf_hist_em')
def test_fetch_ohlc_empty_raises(mock_hist: MagicMock) -> None:
    mock_hist.return_value = pd.DataFrame()
    p = AkshareProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('999999', 5)


@patch('src.providers.akshare_provider.ak.fund_etf_hist_em')
def test_fetch_ohlc_none_raises(mock_hist: MagicMock) -> None:
    """akshare may return None for invalid symbol — verify EmptyDataError"""
    mock_hist.return_value = None
    p = AkshareProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('999999', 5)


@patch('src.providers.akshare_provider.time.sleep')
@patch('src.providers.akshare_provider.ak.fund_etf_hist_em')
def test_retries_then_succeeds(mock_hist: MagicMock, mock_sleep: MagicMock) -> None:
    good_df = pd.DataFrame({
        '日期': pd.to_datetime(['2026-06-04']),
        '开盘': [1.0], '最高': [1.1], '最低': [0.9],
        '收盘': [1.05], '成交量': [10000], '成交额': [10500.0],
    })
    mock_hist.side_effect = [Exception('timeout'), Exception('timeout'), good_df]
    p = AkshareProvider(max_retries=3, base_delay=2.0)
    df = p.fetch_ohlc('512480', 5)
    assert not df.empty
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(2.0)
    mock_sleep.assert_any_call(4.0)


@patch('src.providers.akshare_provider.time.sleep')
@patch('src.providers.akshare_provider.ak.fund_etf_hist_em')
def test_all_retries_exhausted_raises_provider_error(
    mock_hist: MagicMock, mock_sleep: MagicMock,
) -> None:
    mock_hist.side_effect = ConnectionError('network fail')
    p = AkshareProvider(max_retries=3, base_delay=0.01)
    with pytest.raises(ProviderError, match='network fail'):
        p.fetch_ohlc('512480', 5)
    assert mock_hist.call_count == 3


@patch('src.providers.akshare_provider.time.sleep')
@patch('src.providers.akshare_provider.ak.fund_etf_hist_em')
def test_empty_data_not_retried(mock_hist: MagicMock, mock_sleep: MagicMock) -> None:
    mock_hist.return_value = pd.DataFrame()
    p = AkshareProvider(max_retries=3)
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('999999', 5)
    assert mock_hist.call_count == 1
    assert mock_sleep.call_count == 0
