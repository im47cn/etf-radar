"""巨潮个股→行业映射: 解析筛选 + 管线合并容错."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.providers.stock_industry_provider import (
    StockIndustryFetchError,
    fetch_stock_industry,
    parse_industry,
)
from src.market_breadth.stock_industry_pipeline import build_map, run


# ---------- parse_industry ----------

def _df(rows):
    return pd.DataFrame(rows)


def test_parse_picks_latest_cninfo_standard():
    df = _df([
        {'行业门类': '主要消费', '行业大类': '饮料', '分类标准': '巨潮行业分类标准', '变更日期': '2019-11-12'},
        {'行业门类': '消费', '行业大类': '食品', '分类标准': '中证行业分类标准(旧)', '变更日期': '2020-03-16'},
        {'行业门类': '主要消费', '行业大类': '饮料制造', '分类标准': '巨潮行业分类标准', '变更日期': '2021-06-01'},
    ])
    assert parse_industry(df) == {'l1': '主要消费', 'l2': '饮料制造'}


def test_parse_no_cninfo_returns_none():
    df = _df([{'行业门类': 'x', '行业大类': 'y', '分类标准': '中证行业分类标准', '变更日期': '2020-01-01'}])
    assert parse_industry(df) is None


def test_parse_empty_or_nan():
    assert parse_industry(pd.DataFrame()) is None
    df = _df([{'行业门类': None, '行业大类': '饮料', '分类标准': '巨潮行业分类标准', '变更日期': '2021-01-01'}])
    assert parse_industry(df) is None


def test_fetch_wraps_error():
    class Boom:
        def stock_industry_change_cninfo(self, symbol):
            raise ConnectionError('boom')
    with pytest.raises(StockIndustryFetchError):
        fetch_stock_industry('600519', _ak=Boom(), retries=1, delay=0)


# ---------- build_map ----------

def _fetch_factory(mapping: dict, fail: set):
    def fetch(code):
        if code in fail:
            raise StockIndustryFetchError(f'{code} down')
        return mapping.get(code)  # None = 无巨潮归属
    return fetch


def test_build_map_success_and_unmapped():
    fetch = _fetch_factory({'600519': {'l1': '饮料', 'l2': '白酒'}, '000001': None}, fail=set())
    m, unmapped, rep = build_map(['600519', '000001'], {}, max_workers=2, fetch=fetch)
    assert m == {'600519': {'l1': '饮料', 'l2': '白酒'}}
    assert unmapped == ['000001']
    assert rep.fetched == 1


def test_build_map_keeps_cache_on_failure():
    existing = {'600519': {'l1': '旧', 'l2': '旧'}}
    fetch = _fetch_factory({}, fail={'600519'})
    m, _, rep = build_map(['600519'], existing, max_workers=1, fetch=fetch)
    assert m['600519'] == {'l1': '旧', 'l2': '旧'}  # 失败保留旧值
    assert rep.from_cache == 1 and rep.failed == []


def test_build_map_failure_without_cache_counts_failed():
    fetch = _fetch_factory({}, fail={'999999'})
    m, _, rep = build_map(['999999'], {}, max_workers=1, fetch=fetch)
    assert '999999' not in m and rep.failed == ['999999']


def test_build_map_drops_delisted_from_cache():
    existing = {'600519': {'l1': 'a', 'l2': 'b'}, '退市': {'l1': 'x', 'l2': 'y'}}
    fetch = _fetch_factory({'600519': {'l1': 'a', 'l2': 'b'}}, fail=set())
    m, _, _ = build_map(['600519'], existing, max_workers=1, fetch=fetch)
    assert '退市' not in m  # 不在 universe → 剔除


# ---------- run (端到端, 文件) ----------

def test_run_writes_map_file(tmp_path):
    stocks = tmp_path / 'stocks'
    stocks.mkdir()
    (stocks / 'close_series.json').write_text(json.dumps({
        'dates': ['2026-07-01'], 'stocks': {'600519': [1.0], '000001': [2.0]},
    }), encoding='utf-8')
    fetch = _fetch_factory({'600519': {'l1': '饮料', 'l2': '白酒'}, '000001': {'l1': '银行', 'l2': '银行'}}, fail=set())
    out = run(tmp_path, max_workers=2, fetch=fetch)
    doc = json.loads(out.read_text(encoding='utf-8'))
    assert doc['source'] == 'cninfo' and doc['coverage'] == 1.0
    assert doc['map']['600519'] == {'l1': '饮料', 'l2': '白酒'}
