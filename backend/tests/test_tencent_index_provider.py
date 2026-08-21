"""TencentIndexProvider 夹具单测 (禁真实网络, mock requests)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.providers.index_provider import IndexFetchError, TencentIndexProvider


def _fake_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _payload(klines: list[list], key: str = 'day') -> dict:
    return {'code': 0, 'msg': '', 'data': {'sh000985': {key: klines}}}


def test_fetch_close_parses_day_klines() -> None:
    """指数数据落在 day 键; 行元素 [date, open, close, ...] 取第 2 列收盘价."""
    resp = _fake_response(_payload([
        ['2026-08-18', '5100.0', '5150.2', '5160.0', '5090.0', '123000000'],
        ['2026-08-19', '5150.0', '5120.5', '5170.0', '5110.0', '98000000'],
    ]))
    p = TencentIndexProvider(max_retries=0)
    with patch('src.providers.index_provider.requests.get', return_value=resp) as mock_get:
        rows = p.fetch_close('000985')
    assert rows == [(date(2026, 8, 18), 5150.2), (date(2026, 8, 19), 5120.5)]
    # symbol 映射与请求参数
    args, kwargs = mock_get.call_args
    assert args[0] == 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    assert kwargs['params']['param'].startswith('sh000985,day,,,')
    assert kwargs['timeout'] == 10


def test_fetch_close_qfqday_key_compatible() -> None:
    """个股复权键 qfqday 兼容取用 (指数接口偶返回该键)."""
    resp = _fake_response(_payload([['2026-08-19', '1.0', '2.0', '2.5', '0.9', '100']], key='qfqday'))
    p = TencentIndexProvider(max_retries=0)
    with patch('src.providers.index_provider.requests.get', return_value=resp):
        assert p.fetch_close('000985') == [(date(2026, 8, 19), 2.0)]


def test_fetch_close_399_maps_to_sz_prefix() -> None:
    resp = _fake_response({'code': 0, 'data': {'sz399006': {'day': [['2026-08-19', '1', '2600.75', '1', '1', '1']]}}})
    p = TencentIndexProvider(max_retries=0)
    with patch('src.providers.index_provider.requests.get', return_value=resp) as mock_get:
        assert p.fetch_close('399006') == [(date(2026, 8, 19), 2600.75)]
    assert 'sz399006' in mock_get.call_args.kwargs['params']['param']


def test_fetch_close_empty_payload_raises_without_retry() -> None:
    """空 payload 属 IndexFetchError, 直接抛出不重试 (chain 快速切换)."""
    resp = _fake_response({'code': 0, 'data': {}})
    p = TencentIndexProvider(max_retries=2)
    with (
        patch('src.providers.index_provider.requests.get', return_value=resp) as mock_get,
        patch('src.providers.index_provider.time.sleep') as mock_sleep,
        pytest.raises(IndexFetchError, match='empty payload'),
    ):
        p.fetch_close('000985')
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_close_empty_kline_raises() -> None:
    resp = _fake_response({'code': 0, 'data': {'sh000985': {'day': []}}})
    p = TencentIndexProvider(max_retries=0)
    with (
        patch('src.providers.index_provider.requests.get', return_value=resp),
        pytest.raises(IndexFetchError, match='empty kline'),
    ):
        p.fetch_close('000985')


def test_fetch_close_network_error_retries_then_raises() -> None:
    """网络异常走指数退避重试, 耗尽后抛 IndexFetchError 供 chain 落下一级."""
    p = TencentIndexProvider(max_retries=2, base_backoff=0.01)
    with (
        patch('src.providers.index_provider.requests.get', side_effect=ConnectionError('reset')),
        patch('src.providers.index_provider.time.sleep') as mock_sleep,
        pytest.raises(IndexFetchError, match='tencent fetch failed'),
    ):
        p.fetch_close('000985')
    assert mock_sleep.call_count == 2


def test_fetch_close_bad_json_row_raises() -> None:
    """坏行 (日期格式错) 抛 ValueError → 包装为重试路径, 耗尽后 IndexFetchError."""
    resp = _fake_response(_payload([['2026/08/19', '1.0', '2.0']]))
    p = TencentIndexProvider(max_retries=0)
    with (
        patch('src.providers.index_provider.requests.get', return_value=resp),
        pytest.raises(IndexFetchError, match='tencent fetch failed'),
    ):
        p.fetch_close('000985')


def test_chain_three_providers_registered_in_trading_pipeline() -> None:
    """trading pipeline 默认 chain 为三级 (新浪→东财→腾讯), 防回归为两级."""
    import inspect

    from src.trading import pipeline as tp

    src = inspect.getsource(tp)
    assert 'TencentIndexProvider()' in src


def test_chain_three_providers_registered_in_index_series() -> None:
    """market_breadth index_series chain 同样三级注册."""
    import inspect

    from src.market_breadth import index_series as iser

    src = inspect.getsource(iser)
    assert 'TencentIndexProvider()' in src
