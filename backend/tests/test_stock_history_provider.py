"""Provider wraps ak.stock_zh_a_hist with retry + symbol encoding"""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.providers.stock_history_provider import (
    StockHistoryFetchError,
    StockHistoryProvider,
)


def _fake_df(code: str = '002129') -> pd.DataFrame:
    return pd.DataFrame({
        '日期': pd.to_datetime(['2026-04-01', '2026-04-02']),
        '开盘': [12.3, 12.5],
        '最高': [12.65, 12.7],
        '最低': [12.2, 12.4],
        '收盘': [12.5, 12.6],
        '成交量': [5230000, 6100000],
    })


def test_fetch_history_success():
    p = StockHistoryProvider()
    with patch('akshare.stock_zh_a_hist', return_value=_fake_df()):
        bars = p.fetch_history('002129', days=60)
    assert len(bars) == 2
    assert bars[0].o == 12.3
    assert bars[0].c == 12.5
    assert bars[1].v == 6100000


def test_fetch_history_empty_df_raises():
    p = StockHistoryProvider()
    with patch('akshare.stock_zh_a_hist', return_value=pd.DataFrame()):
        with pytest.raises(StockHistoryFetchError):
            p.fetch_history('002129', days=60)


def test_fetch_history_retries_on_exception_then_succeeds():
    p = StockHistoryProvider(max_retries=2, base_backoff=0.001)
    call_count = [0]

    def flaky(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ConnectionError('network')
        return _fake_df()

    with patch('akshare.stock_zh_a_hist', side_effect=flaky):
        bars = p.fetch_history('002129', days=60)
    assert call_count[0] == 2
    assert len(bars) == 2


def test_fetch_history_exhausts_retries():
    p = StockHistoryProvider(max_retries=2, base_backoff=0.001)
    with patch('akshare.stock_zh_a_hist', side_effect=ConnectionError('down')):
        with pytest.raises(StockHistoryFetchError):
            p.fetch_history('002129', days=60)


def test_truncates_to_requested_days():
    """如果 akshare 返回超过 days 行，截取尾部 days 个"""
    df = pd.DataFrame({
        '日期': pd.to_datetime([f'2026-{m:02d}-{d:02d}' for m in [3, 4] for d in range(1, 6)]),
        '开盘': [10.0] * 10, '最高': [10.5] * 10, '最低': [9.5] * 10,
        '收盘': [10.2] * 10, '成交量': [1000] * 10,
    })
    p = StockHistoryProvider()
    with patch('akshare.stock_zh_a_hist', return_value=df):
        bars = p.fetch_history('002129', days=5)
    assert len(bars) == 5
    assert bars[0].date == date(2026, 4, 1)
