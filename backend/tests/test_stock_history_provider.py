"""Provider 包装 ak.stock_zh_a_daily（新浪源）+ 重试 + 前缀映射"""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.providers.stock_history_provider import (
    StockHistoryFetchError,
    StockHistoryProvider,
    to_sina_symbol,
)


def _fake_df() -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.to_datetime(['2026-04-01', '2026-04-02']),
        'open': [12.3, 12.5],
        'high': [12.65, 12.7],
        'low': [12.2, 12.4],
        'close': [12.5, 12.6],
        'volume': [5230000, 6100000],
    })


def test_to_sina_symbol_prefix_mapping():
    assert to_sina_symbol('600519') == 'sh600519'  # 沪市主板
    assert to_sina_symbol('688981') == 'sh688981'  # 科创板
    assert to_sina_symbol('000001') == 'sz000001'  # 深市主板
    assert to_sina_symbol('300750') == 'sz300750'  # 创业板
    assert to_sina_symbol('002129') == 'sz002129'  # 中小板
    assert to_sina_symbol('920000') == 'bj920000'  # 北交所
    assert to_sina_symbol('830799') == 'bj830799'  # 北交所老板


def test_fetch_history_success_passes_sina_symbol():
    p = StockHistoryProvider()
    captured: dict[str, str] = {}

    def fake_daily(symbol: str, adjust: str) -> pd.DataFrame:
        captured['symbol'] = symbol
        captured['adjust'] = adjust
        return _fake_df()

    with patch('akshare.stock_zh_a_daily', side_effect=fake_daily):
        bars = p.fetch_history('002129', days=60)
    assert captured == {'symbol': 'sz002129', 'adjust': 'qfq'}
    assert len(bars) == 2
    assert bars[0].o == 12.3
    assert bars[0].c == 12.5
    assert bars[1].v == 6100000


def test_fetch_history_empty_df_raises():
    p = StockHistoryProvider()
    with patch('akshare.stock_zh_a_daily', return_value=pd.DataFrame()):
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

    with patch('akshare.stock_zh_a_daily', side_effect=flaky):
        bars = p.fetch_history('002129', days=60)
    assert call_count[0] == 2
    assert len(bars) == 2


def test_fetch_history_exhausts_retries():
    p = StockHistoryProvider(max_retries=2, base_backoff=0.001)
    with patch('akshare.stock_zh_a_daily', side_effect=ConnectionError('down')):
        with pytest.raises(StockHistoryFetchError):
            p.fetch_history('002129', days=60)


def test_truncates_to_requested_days():
    """akshare 返回超过 days 行 → 截尾部 days 行"""
    df = pd.DataFrame({
        'date': pd.to_datetime([f'2026-{m:02d}-{d:02d}' for m in [3, 4] for d in range(1, 6)]),
        'open': [10.0] * 10, 'high': [10.5] * 10, 'low': [9.5] * 10,
        'close': [10.2] * 10, 'volume': [1000] * 10,
    })
    p = StockHistoryProvider()
    with patch('akshare.stock_zh_a_daily', return_value=df):
        bars = p.fetch_history('002129', days=5)
    assert len(bars) == 5
    assert bars[0].date == date(2026, 4, 1)
