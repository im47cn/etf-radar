"""HoldingsProvider akshare 封装测试 (全部 mock akshare)"""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.providers.holdings_provider import HoldingsProvider, HoldingsFetchError


def _row(code: str, name: str, weight: float, quarter_tag: str) -> dict:
    return {
        '股票代码': code,
        '股票名称': name,
        '占净值比例': weight,
        '季度': quarter_tag,
    }


@pytest.fixture
def fake_ak_df():
    """模拟 ak.fund_portfolio_hold_em(symbol=, date=YYYY) 返回的 DataFrame。

    akshare 真实返回该年度所有季度行；本 fixture 仅放 2026 年 1 季度。
    """
    return pd.DataFrame([
        _row('002129', 'TCL中环', 8.5, '2026年1季度股票投资明细'),
        _row('603501', '韦尔股份', 7.2, '2026年1季度股票投资明细'),
        _row('300782', '卓胜微',  5.1, '2026年1季度股票投资明细'),
    ])


def test_fetch_returns_holdings(fake_ak_df):
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em',
               return_value=fake_ak_df) as mocked:
        provider = HoldingsProvider()
        snap = provider.fetch(etf_code='512480', etf_name='半导体ETF', quarter=date(2026, 3, 31))
        mocked.assert_called_once_with(symbol='512480', date='2026')
        assert snap.etf_code == '512480'
        assert snap.disclosure_date == date(2026, 3, 31)
        assert len(snap.top_holdings) == 3
        assert snap.top_holdings[0].code == '002129'
        assert snap.top_holdings[0].weight == 8.5


def test_fetch_filters_by_quarter():
    """同年度多季度数据混合时，只取目标季度的行。"""
    df = pd.DataFrame([
        _row('002129', 'TCL中环', 8.5, '2026年1季度股票投资明细'),
        _row('999999', '混入项',  7.0, '2025年4季度股票投资明细'),
    ])
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em', return_value=df):
        provider = HoldingsProvider()
        snap = provider.fetch(etf_code='512480', etf_name='x', quarter=date(2026, 3, 31))
        codes = [h.code for h in snap.top_holdings]
        assert codes == ['002129']


def test_fetch_caps_at_10():
    rows = [_row(f'{i:06d}', f's{i}', 10.0 - i * 0.1, '2026年1季度股票投资明细')
            for i in range(15)]
    big = pd.DataFrame(rows)
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em', return_value=big):
        provider = HoldingsProvider()
        snap = provider.fetch(etf_code='512480', etf_name='x', quarter=date(2026, 3, 31))
        assert len(snap.top_holdings) == 10


def test_fetch_empty_raises():
    empty = pd.DataFrame({'股票代码': [], '股票名称': [], '占净值比例': [], '季度': []})
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em', return_value=empty):
        provider = HoldingsProvider()
        with pytest.raises(HoldingsFetchError):
            provider.fetch(etf_code='512480', etf_name='x', quarter=date(2026, 3, 31))


def test_fetch_quarter_not_disclosed_raises():
    """该年度有数据但目标季度尚未披露 → 抛 HoldingsFetchError 触发上层回退。"""
    df = pd.DataFrame([_row('002129', 'x', 5.0, '2025年4季度股票投资明细')])
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em', return_value=df):
        provider = HoldingsProvider()
        with pytest.raises(HoldingsFetchError) as exc:
            provider.fetch(etf_code='512480', etf_name='x', quarter=date(2026, 3, 31))
        assert 'not disclosed' in str(exc.value)


def test_fetch_akshare_exception_wrapped():
    with patch('src.providers.holdings_provider.ak.fund_portfolio_hold_em',
               side_effect=Exception('network')):
        provider = HoldingsProvider()
        with pytest.raises(HoldingsFetchError) as exc:
            provider.fetch(etf_code='512480', etf_name='x', quarter=date(2026, 3, 31))
        assert 'network' in str(exc.value)
