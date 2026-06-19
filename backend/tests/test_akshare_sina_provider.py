"""AkshareSinaProvider 单元测试"""
import pandas as pd  # type: ignore[import-untyped]
import pytest
from unittest.mock import patch, MagicMock
from src.providers.akshare_sina_provider import AkshareSinaProvider
from src.providers.base import EmptyDataError, ProviderError


@pytest.mark.parametrize('em_code, expected_sina', [
    ('159755', 'sz159755'),
    ('162411', 'sz162411'),
    ('512000', 'sh512000'),
    ('588000', 'sh588000'),
    ('600000', 'sh600000'),
])
def test_to_sina_symbol_mapping(em_code: str, expected_sina: str) -> None:
    assert AkshareSinaProvider._to_sina_symbol(em_code) == expected_sina


def test_to_sina_symbol_unknown_prefix_raises() -> None:
    with pytest.raises(ValueError, match='unknown CN ETF symbol prefix'):
        AkshareSinaProvider._to_sina_symbol('999999')


@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_fetch_ohlc_success(mock_hist: MagicMock) -> None:
    fake = pd.DataFrame({
        'date': pd.to_datetime(['2026-06-17', '2026-06-18']),
        'open': [1.0, 1.05], 'high': [1.1, 1.08],
        'low': [0.9, 1.02], 'close': [1.05, 1.06],
        'volume': [10000, 12000], 'amount': [10500.0, 12700.0],
    })
    mock_hist.return_value = fake
    p = AkshareSinaProvider()
    df = p.fetch_ohlc('512000', 5)
    assert not df.empty
    assert df['amount'].iloc[-1] == 12700.0
    mock_hist.assert_called_once_with(symbol='sh512000')


@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_fetch_ohlc_empty_raises(mock_hist: MagicMock) -> None:
    mock_hist.return_value = pd.DataFrame()
    p = AkshareSinaProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('512000', 5)


@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_fetch_ohlc_none_raises(mock_hist: MagicMock) -> None:
    mock_hist.return_value = None
    p = AkshareSinaProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('512000', 5)


@patch('src.providers.akshare_sina_provider.time.sleep')
@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_retries_then_succeeds(mock_hist: MagicMock, mock_sleep: MagicMock) -> None:
    good = pd.DataFrame({
        'date': pd.to_datetime(['2026-06-18']),
        'open': [1.0], 'high': [1.1], 'low': [0.9],
        'close': [1.05], 'volume': [10000], 'amount': [10500.0],
    })
    mock_hist.side_effect = [Exception('timeout'), Exception('timeout'), good]
    p = AkshareSinaProvider(max_retries=3, base_delay=2.0)
    df = p.fetch_ohlc('512000', 5)
    assert not df.empty
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(2.0)
    mock_sleep.assert_any_call(4.0)


@patch('src.providers.akshare_sina_provider.time.sleep')
@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_all_retries_exhausted_raises(
    mock_hist: MagicMock, mock_sleep: MagicMock,
) -> None:
    mock_hist.side_effect = ConnectionError('network fail')
    p = AkshareSinaProvider(max_retries=3, base_delay=0.01)
    with pytest.raises(ProviderError, match='network fail'):
        p.fetch_ohlc('512000', 5)
    assert mock_hist.call_count == 3


@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_lookback_days_tail_applied(mock_hist: MagicMock) -> None:
    """sina 返回全历史，应按 lookback_days * 1.6 截尾"""
    n_rows = 1000
    dates = pd.date_range('2020-01-01', periods=n_rows, freq='D')
    fake = pd.DataFrame({
        'date': dates,
        'open': [1.0] * n_rows, 'high': [1.0] * n_rows,
        'low': [1.0] * n_rows, 'close': [1.0] * n_rows,
        'volume': [100] * n_rows, 'amount': [100.0] * n_rows,
    })
    mock_hist.return_value = fake
    p = AkshareSinaProvider()
    df = p.fetch_ohlc('512000', lookback_days=100)
    assert len(df) == 160
