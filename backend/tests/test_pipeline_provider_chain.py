"""provider chain 集成测试: _collect_cn_ohlc 的多源 fallback 行为"""
import pandas as pd  # type: ignore[import-untyped]
from unittest.mock import MagicMock, patch
from src.models import CnEtfConfig, ThemeConfig
from src.pipeline import _collect_cn_ohlc
from src.providers.base import EmptyDataError, EtfDataProvider, ProviderError


def _make_provider(name: str, success_codes: set[str]) -> EtfDataProvider:
    """Mock provider: 对 success_codes 返回 OHLC，其他 raise ProviderError"""
    mock = MagicMock(spec=EtfDataProvider)
    mock.name = name

    def fetch(symbol: str, lookback_days: int) -> pd.DataFrame:
        if symbol in success_codes:
            return pd.DataFrame({
                'date': pd.to_datetime(['2026-06-18'], utc=True),
                'open': [1.0], 'high': [1.1], 'low': [0.9],
                'close': [1.05], 'volume': [10000], 'amount': [10500.0],
            })
        raise ProviderError(f'mock {name} fail for {symbol}')

    mock.fetch_ohlc.side_effect = fetch
    return mock


def _themes_with(codes: list[str]) -> list[ThemeConfig]:
    return [
        ThemeConfig(
            id='t1', name='T1', us_etfs=['SPY'], primary_us='SPY', tags=[], note='',
            cn_etfs=[CnEtfConfig(code=c, name=c, tracking='', match_type='exact') for c in codes],
        )
    ]


@patch('src.pipeline.time.sleep')
def test_all_primary_success(mock_sleep: MagicMock) -> None:
    """所有 symbol 都在主源拿到 → fallback_map={}, failed=[]"""
    themes = _themes_with(['512000', '159755'])
    primary = _make_provider('akshare-em', {'512000', '159755'})
    secondary = _make_provider('akshare-sina', set())
    ohlc, fallback_map, failed = _collect_cn_ohlc(themes, [primary, secondary])
    assert set(ohlc.keys()) == {'512000', '159755'}
    assert fallback_map == {}
    assert failed == []
    secondary.fetch_ohlc.assert_not_called()


@patch('src.pipeline.time.sleep')
def test_partial_fallback(mock_sleep: MagicMock) -> None:
    """部分主源失败，备用源接力 → fallback_map 记录正确"""
    themes = _themes_with(['512000', '159755', '588000'])
    primary = _make_provider('akshare-em', {'512000'})
    secondary = _make_provider('akshare-sina', {'159755', '588000'})
    ohlc, fallback_map, failed = _collect_cn_ohlc(themes, [primary, secondary])
    assert set(ohlc.keys()) == {'512000', '159755', '588000'}
    assert fallback_map == {'159755': 'akshare-sina', '588000': 'akshare-sina'}
    assert failed == []


@patch('src.pipeline.time.sleep')
def test_both_sources_fail(mock_sleep: MagicMock) -> None:
    """双源都失败 → failed_symbols 含该 symbol"""
    themes = _themes_with(['512000', '159755'])
    primary = _make_provider('akshare-em', {'512000'})
    secondary = _make_provider('akshare-sina', set())
    ohlc, fallback_map, failed = _collect_cn_ohlc(themes, [primary, secondary])
    assert set(ohlc.keys()) == {'512000'}
    assert fallback_map == {}
    assert failed == ['159755']


@patch('src.pipeline.time.sleep')
def test_immediate_switch_no_60s_wait(mock_sleep: MagicMock) -> None:
    """验证不再有 60s second-pass: sleep 调用不应出现 60.0 数值"""
    themes = _themes_with(['512000', '159755'])
    primary = _make_provider('akshare-em', {'512000'})
    secondary = _make_provider('akshare-sina', {'159755'})
    _collect_cn_ohlc(themes, [primary, secondary])
    sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
    assert all(v < 5.0 for v in sleep_values), f'unexpected long sleep: {sleep_values}'


@patch('src.pipeline.time.sleep')
def test_secondary_tried_only_when_primary_fails(mock_sleep: MagicMock) -> None:
    """主源成功时，备用源不应被尝试"""
    themes = _themes_with(['512000'])
    primary = _make_provider('akshare-em', {'512000'})
    secondary = MagicMock(spec=EtfDataProvider)
    secondary.name = 'akshare-sina'
    _collect_cn_ohlc(themes, [primary, secondary])
    secondary.fetch_ohlc.assert_not_called()


@patch('src.pipeline.time.sleep')
def test_empty_data_treated_as_failure(mock_sleep: MagicMock) -> None:
    """主源返回 EmptyDataError 时应尝试备用源（不是直接 raise）"""
    themes = _themes_with(['512000'])
    primary = MagicMock(spec=EtfDataProvider)
    primary.name = 'akshare-em'
    primary.fetch_ohlc.side_effect = EmptyDataError('empty')
    secondary = _make_provider('akshare-sina', {'512000'})
    ohlc, fallback_map, failed = _collect_cn_ohlc(themes, [primary, secondary])
    assert '512000' in ohlc
    assert fallback_map == {'512000': 'akshare-sina'}
    assert failed == []
