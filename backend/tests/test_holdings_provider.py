"""HoldingsProvider akshare 封装测试 (全部 mock akshare)"""
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.providers.holdings_provider import HoldingsProvider, HoldingsFetchError


@pytest.fixture
def fake_ak_df():
    """模拟 ak.fund_portfolio_hold_em 返回的 DataFrame。"""
    return pd.DataFrame({
        '股票代码': ['002129', '603501', '300782'],
        '股票名称': ['TCL中环', '韦尔股份', '卓胜微'],
        '占净值比例': [8.5, 7.2, 5.1],
    })


def test_fetch_returns_holdings(fake_ak_df):
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em',
               return_value=fake_ak_df) as mocked:
        provider = HoldingsProvider()
        snap = provider.fetch(etf_code='512480', etf_name='半导体ETF', quarter=date(2026, 3, 31))
        mocked.assert_called_once_with(code='512480', date='20260331')
        assert snap.etf_code == '512480'
        assert snap.disclosure_date == date(2026, 3, 31)
        assert len(snap.top_holdings) == 3
        assert snap.top_holdings[0].code == '002129'
        assert snap.top_holdings[0].weight == 8.5


def test_fetch_caps_at_10(fake_ak_df):
    big = pd.DataFrame({
        '股票代码': [f'{i:06d}' for i in range(15)],
        '股票名称': [f's{i}' for i in range(15)],
        '占净值比例': [10.0 - i * 0.1 for i in range(15)],
    })
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em', return_value=big):
        provider = HoldingsProvider()
        snap = provider.fetch(etf_code='512480', etf_name='x', quarter=date(2026, 3, 31))
        assert len(snap.top_holdings) == 10


def test_fetch_empty_raises():
    empty = pd.DataFrame({'股票代码': [], '股票名称': [], '占净值比例': []})
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em', return_value=empty):
        provider = HoldingsProvider()
        with pytest.raises(HoldingsFetchError):
            provider.fetch(etf_code='512480', etf_name='x', quarter=date(2026, 3, 31))


def test_fetch_akshare_exception_wrapped():
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em',
               side_effect=Exception('network')):
        provider = HoldingsProvider()
        with pytest.raises(HoldingsFetchError) as exc:
            provider.fetch(etf_code='512480', etf_name='x', quarter=date(2026, 3, 31))
        assert 'network' in str(exc.value)
