"""pipeline.py 单测: run() 端到端 (mock provider chain / ohlcv 装载 / trading.json 契约 / 降级)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema
import numpy as np
import pytest

from src.providers.base import ProviderError
from src.trading.pipeline import INDEX_LOOKBACK, fetch_index_close, load_universe, load_vol_map, run
from tests.test_trading_fixtures import candidate_closes, defense_index, offense_index, volumes

SCHEMA = Path(__file__).parent / 'schemas' / 'trading.schema.json'
D0 = date(2025, 1, 1)


class FakeIndexProvider:
    """可控指数 provider: series 按代码注入, fail 抛错, stale 返回 2016 截断序列。

    日期锚定"今天往前推", 保证默认序列末条新鲜 (过新鲜度护栏)。
    """

    name = 'fake-index'
    STALE_LAST = date(2016, 6, 30)  # 新浪 sh000985 实测截断点 (M5 发现)

    def __init__(self, series: dict[str, list[float]], fail: set[str] | None = None,
                 stale: set[str] | None = None) -> None:
        self._series = series
        self._fail = fail or set()
        self._stale = stale or set()

    def fetch_close(self, code: str) -> list[tuple[date, float]]:
        if code in self._fail or code not in self._series:
            raise RuntimeError(f'{code} boom')
        shape = self._series[code]
        if code in self._stale:
            start = self.STALE_LAST - timedelta(days=len(shape) - 1)
            return [(start + timedelta(days=i), v) for i, v in enumerate(shape)]
        start = datetime.now(ZoneInfo('Asia/Shanghai')).date() - timedelta(days=len(shape))
        return [(start + timedelta(days=i), v) for i, v in enumerate(shape)]


def _provider(shape: list[float], fail: set[str] | None = None, stale: set[str] | None = None) -> FakeIndexProvider:
    return FakeIndexProvider(
        {'000300': shape, '000905': shape, '399006': shape, '000985': shape}, fail, stale
    )


def _write_ohlcv(root: Path, code: str, closes: list[float], name_vol: bool = True) -> None:
    d = root / 'stocks' / 'ohlcv'
    d.mkdir(parents=True, exist_ok=True)
    vols = volumes(len(closes)) if name_vol else np.full(len(closes), 1e6)
    bars = [
        {
            'd': (D0 + timedelta(days=i)).isoformat(), 'o': c, 'h': c * 1.001, 'l': c * 0.999,
            'c': c, 'v': float(vols[i]), 'amt': 2e8,
        }
        for i, c in enumerate(closes)
    ]
    (d / f'{code}.json').write_text(
        json.dumps({'schema_version': '1.0', 'code': code, 'bars': bars}), encoding='utf-8'
    )


def _setup_env_files(root: Path) -> None:
    (root / 'latest').mkdir(parents=True, exist_ok=True)
    temp = {
        'schema_version': '2.0',
        'periods': {
            k: {'market': [{'date': '2026-08-18', 'rate': v}]}
            for k, v in (('ma5', 90.0), ('ma20', 81.2), ('ma60', 55.0), ('ma120', 48.0))
        },
    }
    (root / 'latest' / 'market_temperature.json').write_text(json.dumps(temp), encoding='utf-8')
    hold = {'schema_version': '1.0', 'generated_at': '2026-08-18T00:00:00+00:00',
            'stocks': {'600001': {'vol_forecast_ann': 0.3}}}
    (root / 'stocks').mkdir(parents=True, exist_ok=True)
    (root / 'stocks' / 'holdings_indicators.json').write_text(json.dumps(hold), encoding='utf-8')


def test_run_offense_full_contract(tmp_path: Path) -> None:
    _write_ohlcv(tmp_path, '600001', candidate_closes())
    _write_ohlcv(tmp_path, '600002', [50.0] * 300)  # 下跌/横盘: 不进漏斗后段
    _setup_env_files(tmp_path)
    out = run(
        tmp_path,
        index_providers=[_provider(offense_index())],
        spot_names={'600001': '贵州测试', '600002': 'ST测试'},
    )
    assert out == tmp_path / 'latest' / 'trading.json'
    doc = json.loads(out.read_text(encoding='utf-8'))
    jsonschema.validate(doc, json.loads(SCHEMA.read_text(encoding='utf-8')))

    env = doc['environment']
    assert env['regime'] == 'offense'
    assert len(env['indices']) == 3
    assert env['indices'][0]['template_pass'] == 7  # 指数无 RS
    assert env['breadth'] == {'ma20_pct': 0.812, 'ma60_pct': 0.55, 'ma120_pct': 0.48,
                              'source': 'market_temperature.json'}
    assert env['source_status']['indices'] == 'ok'
    assert env['source_status']['rs_benchmark'] == 'ok'
    assert env['source_status']['spot'] == 'ok'
    assert env['source_status']['breadth'] == 'ok'
    assert env['source_status']['universe'] == 'ok'
    assert env['source_status']['vol'] == 'ok'

    # ST 股被剔 -> 候选只有 600001
    assert [c['code'] for c in doc['candidates']] == ['600001']
    cand = doc['candidates'][0]
    assert cand['name'] == '贵州测试'
    assert cand['vol_forecast_ann'] == 0.3
    assert cand['rs_pct'] is not None
    assert doc['universe_stats'] == {'total': 2, 'tradable': 1, 'stage2': 1, 'vcp': 1, 'top': 1}


def test_run_defense_gating_freezes_states(tmp_path: Path) -> None:
    _write_ohlcv(tmp_path, '600001', candidate_closes())
    _setup_env_files(tmp_path)
    run(
        tmp_path,
        index_providers=[_provider(defense_index())],
        spot_names={'600001': '贵州测试'},
    )
    doc = json.loads((tmp_path / 'latest' / 'trading.json').read_text(encoding='utf-8'))
    assert doc['environment']['regime'] == 'defense'
    # VCP 原始状态 near_buy_zone, defense 档冻结为 watch (spec §1.1 硬 gating)
    assert all(c['state'] == 'watch' for c in doc['candidates'])


def test_run_environment_failure_raises(tmp_path: Path) -> None:
    """三指数全 chain 失败 -> ProviderError (核心失败, CI 可见)。"""
    _setup_env_files(tmp_path)
    with pytest.raises(ProviderError, match='environment'):
        run(tmp_path, index_providers=[_provider(offense_index(), fail={'000300', '000905', '399006'})],
            spot_names={})


def test_run_single_index_alive_still_ok(tmp_path: Path) -> None:
    """1 只指数失败仍可判档 (2 只可用), source_status=partial。"""
    _write_ohlcv(tmp_path, '600001', candidate_closes())
    _setup_env_files(tmp_path)
    run(
        tmp_path,
        index_providers=[_provider(offense_index(), fail={'399006'})],
        spot_names={'600001': '贵州测试'},
    )
    doc = json.loads((tmp_path / 'latest' / 'trading.json').read_text(encoding='utf-8'))
    assert doc['environment']['source_status']['indices'] == 'partial'
    assert len(doc['environment']['indices']) == 2


def test_run_rs_benchmark_missing_degrades(tmp_path: Path) -> None:
    _write_ohlcv(tmp_path, '600001', candidate_closes())
    _setup_env_files(tmp_path)
    run(
        tmp_path,
        index_providers=[_provider(offense_index(), fail={'000985'})],
        spot_names={'600001': '贵州测试'},
    )
    doc = json.loads((tmp_path / 'latest' / 'trading.json').read_text(encoding='utf-8'))
    assert doc['environment']['source_status']['rs_benchmark'] == 'missing'
    assert doc['candidates'][0]['rs_pct'] is None  # RS 整体降级
    assert doc['candidates'][0]['composite_score'] == 6.3  # RS 挂 -> pass 7 + 剔 RS 项归一


def test_run_empty_universe_degrades_not_raises(tmp_path: Path) -> None:
    """ohlcv 未就绪 (M0 未跑): 产出空候选 + universe=empty, 不阻塞环境页。"""
    _setup_env_files(tmp_path)
    run(tmp_path, index_providers=[_provider(offense_index())], spot_names={})
    doc = json.loads((tmp_path / 'latest' / 'trading.json').read_text(encoding='utf-8'))
    assert doc['candidates'] == []
    assert doc['universe_stats']['total'] == 0
    assert doc['environment']['source_status']['universe'] == 'empty'


def test_run_breadth_missing_degrades(tmp_path: Path) -> None:
    """market_temperature.json 缺失 -> breadth null + 标记。"""
    _write_ohlcv(tmp_path, '600001', candidate_closes())
    (tmp_path / 'stocks').mkdir(parents=True, exist_ok=True)
    run(tmp_path, index_providers=[_provider(offense_index())], spot_names={'600001': 'x'})
    doc = json.loads((tmp_path / 'latest' / 'trading.json').read_text(encoding='utf-8'))
    assert doc['environment']['breadth'] is None
    assert doc['environment']['source_status']['breadth'] == 'missing'


def test_load_universe_skips_corrupt(tmp_path: Path) -> None:
    d = tmp_path / 'stocks' / 'ohlcv'
    d.mkdir(parents=True)
    _write_ohlcv(tmp_path, '600001', [10.0] * 260)
    (d / 'bad.json').write_text('{corrupt', encoding='utf-8')
    (d / 'nolist.json').write_text(json.dumps({'code': '600009', 'bars': []}), encoding='utf-8')
    u = load_universe(d)
    assert set(u) == {'600001', '600009'}  # 空 bars 合法 (total 计数), 损坏文件跳过
    assert len(u['600001'].close) == 260


def test_load_universe_missing_dir(tmp_path: Path) -> None:
    assert load_universe(tmp_path / 'nope') == {}


def test_load_vol_map(tmp_path: Path) -> None:
    _setup_env_files(tmp_path)
    assert load_vol_map(tmp_path) == {'600001': 0.3}
    assert load_vol_map(tmp_path / 'missing') == {}


def test_index_lookback_window() -> None:
    """指数序列截尾 INDEX_LOOKBACK 根 (防全历史拖慢计算)。"""
    series = offense_index(1000)
    p = FakeIndexProvider({'000300': series})
    rows = p.fetch_close('000300')
    arr = fetch_index_close('000300', [p])
    assert arr is not None
    assert len(arr) == INDEX_LOOKBACK
    assert float(arr[-1]) == rows[-1][1]


def test_fetch_spot_names_strips_prefix(monkeypatch) -> None:
    """新浪 spot 代码剥前缀 -> {code: name}。"""
    import akshare as ak
    import pandas as pd

    import src.trading.pipeline as pl

    monkeypatch.setattr(
        ak, 'stock_zh_a_spot',
        lambda: pd.DataFrame({'代码': ['sh600519', 'sz000001', 'bj830799'], '名称': ['贵州测试', '平安测试', '北交测试']}),
    )
    assert pl.fetch_spot_names() == {'600519': '贵州测试', '000001': '平安测试', '830799': '北交测试'}


def test_default_spot_ok(monkeypatch) -> None:
    import src.trading.pipeline as pl

    monkeypatch.setattr(pl, 'fetch_spot_names', lambda: {'600519': 'x'})
    assert pl._default_spot() == ({'600519': 'x'}, True)


def test_default_spot_degrades_on_error(monkeypatch) -> None:
    import src.trading.pipeline as pl

    def boom() -> dict[str, str]:
        raise RuntimeError('network down')

    monkeypatch.setattr(pl, 'fetch_spot_names', boom)
    assert pl._default_spot() == ({}, False)


def test_run_constructs_default_providers(monkeypatch, tmp_path: Path) -> None:
    """index_providers=None 时走默认 chain 构造 (真 IndexProvider/EmIndexProvider)。"""
    _write_ohlcv(tmp_path, '600001', candidate_closes())
    _setup_env_files(tmp_path)
    import src.providers.index_provider as ip

    fake = _provider(offense_index())
    made: list[int] = []

    def _mk() -> FakeIndexProvider:
        made.append(1)
        return fake

    monkeypatch.setattr(ip, 'IndexProvider', _mk)
    monkeypatch.setattr(ip, 'EmIndexProvider', _mk)
    run(tmp_path, spot_names={'600001': 'x'})
    assert len(made) == 2  # 默认 chain 两个 provider 都被构造


def test_main_invokes_run(monkeypatch, tmp_path: Path) -> None:
    import sys

    import src.trading.pipeline as pl

    calls: list[Path] = []
    monkeypatch.setattr(pl, 'run', lambda root: calls.append(root))
    monkeypatch.setattr(sys, 'argv', ['pipeline', '--data-root', str(tmp_path)])
    pl.main()
    assert calls == [tmp_path]


def test_fetch_index_close_stale_falls_to_next_provider() -> None:
    """新浪 sh000985 式截断 (末条 2016): 该源视为失败, chain 切换到下一源。"""
    stale = FakeIndexProvider({'000985': offense_index()}, stale={'000985'})
    fresh = FakeIndexProvider({'000985': offense_index()})
    arr = fetch_index_close('000985', [stale, fresh])
    assert arr is not None
    assert len(arr) == INDEX_LOOKBACK
    assert float(arr[-1]) == pytest.approx(offense_index()[-1], rel=1e-12)  # 来自新源而非陈旧源


def test_fetch_index_close_all_stale_returns_none() -> None:
    """全链陈旧 -> None (走 RS 降级路径), 不静默用坏数据。"""
    stale = FakeIndexProvider({'000985': offense_index()}, stale={'000985'})
    assert fetch_index_close('000985', [stale]) is None


def test_run_stale_benchmark_degrades_rs(tmp_path: Path) -> None:
    """000985 新鲜度护栏触发 (provider 成功返回 2016 截断) -> rs_benchmark=missing + rs_pct null。"""
    _write_ohlcv(tmp_path, '600001', candidate_closes())
    _setup_env_files(tmp_path)
    run(
        tmp_path,
        index_providers=[_provider(offense_index(), stale={'000985'})],
        spot_names={'600001': '贵州测试'},
    )
    doc = json.loads((tmp_path / 'latest' / 'trading.json').read_text(encoding='utf-8'))
    assert doc['environment']['source_status']['rs_benchmark'] == 'missing'
    assert doc['candidates'][0]['rs_pct'] is None
    # 三环境指数未受影响 (新鲜)
    assert doc['environment']['source_status']['indices'] == 'ok'
    assert doc['environment']['regime'] == 'offense'
