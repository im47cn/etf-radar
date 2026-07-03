"""市场宽度管线测试: 映射 / provider 解析 / 聚合口径."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.market_breadth.industry_mapping import L1_ORDER, L2_TO_L1, OTHER_L1, to_l1
from src.market_breadth.pipeline import compute_market_temperature
from src.providers.base import EmptyDataError, ProviderError
from src.providers.dapanyuntu_provider import BreadthRaw, DapanyuntuProvider, _parse


# ---------- 映射表 ----------

def test_mapping_has_86_l2_and_26_l1():
    assert len(L2_TO_L1) == 86
    assert len(L1_ORDER) == 26
    assert len(set(L2_TO_L1.values())) == 26


def test_to_l1_known_and_unknown():
    assert to_l1('半导体') == '电子'
    assert to_l1('不存在的行业') == OTHER_L1


# ---------- provider 解析 ----------

def test_parse_ok():
    payload = {'data': [[0, 0, 42.0]], 'dates': ['2026-07-01'], 'industries': ['半导体']}
    raw = _parse(payload)
    assert raw.dates == ['2026-07-01'] and raw.industries == ['半导体']


@pytest.mark.parametrize('payload', [
    {'data': [], 'dates': ['d'], 'industries': ['i']},
    {'data': [[0, 0, 1]], 'dates': [], 'industries': ['i']},
    {'dates': ['d'], 'industries': ['i']},
])
def test_parse_empty_raises(payload):
    with pytest.raises(EmptyDataError):
        _parse(payload)


def test_fetch_breadth_403_raises_provider_error():
    prov = DapanyuntuProvider(max_retries=2, base_delay=0)
    with patch('urllib.request.urlopen', side_effect=__import__('urllib.error', fromlist=['HTTPError']).HTTPError(
            'u', 403, 'Forbidden', {}, None)):
        with pytest.raises(ProviderError):
            prov.fetch_breadth()


def test_fetch_breadth_ok():
    prov = DapanyuntuProvider(max_retries=1, base_delay=0)
    body = json.dumps({'data': [[0, 0, 40.0]], 'dates': ['2026-07-01'], 'industries': ['半导体']}).encode()
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    with patch('urllib.request.urlopen', return_value=resp):
        raw = prov.fetch_breadth()
    assert raw.industries == ['半导体']


# ---------- 聚合口径 ----------

def _raw():
    # 2 日 x 3 行业; 半导体+消费电子 -> 电子, 银行 -> 银行
    # 三元组 [date_idx, industry_idx, value]; 含一个 0 值(无数据)和一个缺失位
    return BreadthRaw(
        dates=['2026-07-01', '2026-07-02'],
        industries=['半导体', '消费电子', '银行'],
        data=[
            [0, 0, 40.0], [1, 0, 50.0],   # 半导体
            [0, 1, 60.0], [1, 1, 0.0],    # 消费电子 (day1 无数据=0)
            [0, 2, 10.0],                 # 银行 (day1 缺失)
        ],
    )


def test_zero_and_missing_become_null():
    snap = compute_market_temperature(_raw())
    l2 = {r['name']: r for r in snap['industries_l2']}
    # 消费电子 day1=0 -> null; 银行 day1 缺失 -> null
    assert l2['消费电子']['series'] == [60.0, None]
    assert l2['银行']['series'] == [10.0, None]


def test_l1_equal_weight_mean():
    snap = compute_market_temperature(_raw())
    l1 = {r['name']: r for r in snap['industries_l1']}
    # 电子 day0 = mean(40,60)=50.0; day1 = mean(50) (消费电子=null 被过滤) =50.0
    assert l1['电子']['series'] == [50.0, 50.0]
    assert l1['银行']['series'] == [10.0, None]


def test_market_mean_filters_zero_and_missing():
    snap = compute_market_temperature(_raw())
    m = {d['date']: d['rate'] for d in snap['market']}
    # day0 = mean(40,60,10)=36.7; day1 有效值只有半导体50 -> 50.0
    assert m['2026-07-01'] == pytest.approx(36.7)
    assert m['2026-07-02'] == 50.0


def test_industries_sorted_by_latest_desc():
    snap = compute_market_temperature(_raw())
    latests = [r['latest'] for r in snap['industries_l2']]
    non_null = [x for x in latests if x is not None]
    assert non_null == sorted(non_null, reverse=True)


def test_snapshot_shape():
    snap = compute_market_temperature(_raw())
    assert snap['schema_version'] == '1.0'
    assert snap['metric'] == 'ma20_above_ratio'
    assert len(snap['market']) == len(snap['dates']) == 2
    for r in snap['industries_l1'] + snap['industries_l2']:
        assert len(r['series']) == 2
