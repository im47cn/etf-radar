"""environment.py 单测: 档位规则 / defense 硬 gating / 宽度佐证降级 (spec §1.1)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.providers.base import ProviderError
from src.trading.environment import (
    INDEX_CODES,
    apply_defense_gating,
    classify_regime,
    compute_environment,
    read_breadth,
)
from tests.test_trading_fixtures import defense_index, geo, moderate_index, offense_index


def test_classify_regime_rules() -> None:
    assert classify_regime([7, 6, 3]) == 'offense'  # 2 只 >=6
    assert classify_regime([6, 6, 0]) == 'offense'  # 边界: 6 计进攻票
    assert classify_regime([3, 2, 7]) == 'defense'  # 2 只 <=3
    assert classify_regime([6, 3, 4]) == 'neutral'
    assert classify_regime([7, 3, 4]) == 'neutral'  # 各只分布分散


def test_compute_environment_offense() -> None:
    closes = {code: np.array(offense_index()) for code in INDEX_CODES}
    env = compute_environment(closes)
    assert env['regime'] == 'offense'
    assert len(env['indices']) == 3
    first = env['indices'][0]
    assert first['code'] == '000300'
    assert first['name'] == '沪深300'
    assert first['template_pass'] == 7  # 上涨 7 条过, 第 7 条 (RS) 恒 False
    assert first['criteria'][6] is False
    assert first['close'] == pytest.approx(closes['000300'][-1], rel=1e-6)


def test_compute_environment_defense() -> None:
    closes = {code: np.array(defense_index()) for code in INDEX_CODES}
    env = compute_environment(closes)
    assert env['regime'] == 'defense'
    assert all(e['template_pass'] == 1 for e in env['indices'])  # 仅条8 (均线距离)


def test_compute_environment_neutral_mixed() -> None:
    """进攻 1 (pass 7) / 中性 1 (pass 5) / 防守 1 (pass 1) -> 双方均不足 2 -> neutral。"""
    closes = {
        '000300': np.array(offense_index()),
        '000905': np.array(moderate_index()),
        '399006': np.array(defense_index()),
    }
    env = compute_environment(closes)
    passes = sorted(e['template_pass'] for e in env['indices'])
    assert passes == [1, 5, 7]
    assert env['regime'] == 'neutral'


def test_compute_environment_two_alive_ok() -> None:
    """单只指数缺数据仍可判档位 (>=2 只可用)。"""
    closes = {'000300': np.array(offense_index()), '399006': np.array(offense_index())}
    env = compute_environment(closes)
    assert env['regime'] == 'offense'
    assert len(env['indices']) == 2


def test_compute_environment_too_few_raises() -> None:
    with pytest.raises(ProviderError, match='environment'):
        compute_environment({'000300': np.array(offense_index())})


def test_compute_environment_short_series_dropped() -> None:
    """数据过短 (trend None) 的指数视为不可用; 2 只短 -> raise。"""
    with pytest.raises(ProviderError):
        compute_environment({'000300': np.array(geo(100)), '000905': np.array(offense_index())})


def test_apply_defense_gating_freezes_states() -> None:
    cands = [
        {'code': 'A', 'state': 'in_buy_zone'},
        {'code': 'B', 'state': 'near_buy_zone'},
        {'code': 'C', 'state': 'watch'},
    ]
    out = apply_defense_gating(cands, 'defense')
    assert [c['state'] for c in out] == ['watch', 'watch', 'watch']
    # 不改入参
    assert cands[0]['state'] == 'in_buy_zone'


def test_apply_defense_gating_noop_offense() -> None:
    cands = [{'code': 'A', 'state': 'in_buy_zone'}]
    assert apply_defense_gating(cands, 'offense')[0]['state'] == 'in_buy_zone'
    assert apply_defense_gating(cands, 'neutral')[0]['state'] == 'in_buy_zone'


def _write_temperature(root: Path) -> None:
    doc = {
        'schema_version': '2.0',
        'periods': {
            k: {'market': [{'date': '2026-08-18', 'rate': v}]}
            for k, v in (('ma5', 90.1), ('ma20', 81.2), ('ma60', 55.0), ('ma120', 48.0))
        },
    }
    (root / 'latest').mkdir(parents=True, exist_ok=True)
    (root / 'latest' / 'market_temperature.json').write_text(json.dumps(doc), encoding='utf-8')


def test_read_breadth_ok(tmp_path: Path) -> None:
    _write_temperature(tmp_path)
    b = read_breadth(tmp_path)
    assert b is not None
    assert b['ma20_pct'] == 0.812
    assert b['ma60_pct'] == 0.55
    assert b['ma120_pct'] == 0.48
    assert b['source'] == 'market_temperature.json'


def test_read_breadth_carries_asof_and_stale(tmp_path: Path) -> None:
    """as_of/stale 透传: 前端据此展示数据时点, 与温度页对数可判断陈旧。"""
    doc = {
        'schema_version': '2.0',
        'as_of': '2026-08-19',
        'stale': False,
        'periods': {
            k: {'market': [{'date': '2026-08-19', 'rate': v}]}
            for k, v in (('ma20', 50.2), ('ma60', 32.7), ('ma120', 17.5))
        },
    }
    (tmp_path / 'latest').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'latest' / 'market_temperature.json').write_text(json.dumps(doc), encoding='utf-8')
    b = read_breadth(tmp_path)
    assert b is not None
    assert b['as_of'] == '2026-08-19'
    assert b['stale'] is False
    assert b['ma20_pct'] == 0.502


def test_read_breadth_trailing_none_rate_skipped(tmp_path: Path) -> None:
    """末条 rate=None (当日未算完) 不降级整组, 取最后非空值。"""
    doc = {
        'schema_version': '2.0',
        'periods': {
            k: {'market': [{'date': '2026-08-18', 'rate': v}, {'date': '2026-08-19', 'rate': None}]}
            for k, v in (('ma20', 81.2), ('ma60', 48.6), ('ma120', 24.3))
        },
    }
    (tmp_path / 'latest').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'latest' / 'market_temperature.json').write_text(json.dumps(doc), encoding='utf-8')
    b = read_breadth(tmp_path)
    assert b is not None
    assert b['ma20_pct'] == 0.812


def test_read_breadth_missing_file(tmp_path: Path) -> None:
    assert read_breadth(tmp_path) is None


def test_read_breadth_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / 'latest').mkdir(parents=True)
    (tmp_path / 'latest' / 'market_temperature.json').write_text('{bad json', encoding='utf-8')
    assert read_breadth(tmp_path) is None


def test_read_breadth_empty_market_series(tmp_path: Path) -> None:
    (tmp_path / 'latest').mkdir(parents=True)
    doc = {'periods': {k: {'market': []} for k in ('ma5', 'ma20', 'ma60', 'ma120')}}
    (tmp_path / 'latest' / 'market_temperature.json').write_text(json.dumps(doc), encoding='utf-8')
    assert read_breadth(tmp_path) is None
