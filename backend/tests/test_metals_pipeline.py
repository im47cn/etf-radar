"""metals 管线测试: 组件级降级 + cn_side 提取 + 落盘."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.metals.pipeline import compute_metals, run
from src.providers.base import EmptyDataError

N = 1300  # > GSR_WINDOW, 使 5y 分位有值


def _make_df(start_price: float, drift: float = 0.001) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = start_price * np.cumprod(1.0 + drift + rng.normal(0, 0.01, N))
    dates = pd.bdate_range('2021-01-01', periods=N)
    return pd.DataFrame({
        'date': dates, 'open': close, 'high': close, 'low': close,
        'close': close, 'volume': 0.0, 'amount': 0.0,
    })


class FakeProvider:
    """全部 symbol 成功; 指定 symbol 抛 EmptyDataError 模拟降级."""

    name = 'fake'

    def __init__(self, fail: set[str] = frozenset()) -> None:
        self.fail = fail

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        if symbol in self.fail:
            raise EmptyDataError(f'no data for {symbol}')
        base = {'GLD': 200.0, 'SLV': 20.0, 'GDX': 40.0, 'TIP': 107.0, 'DX-Y.NYB': 104.0}[symbol]
        return _make_df(base)


def _closes(provider: FakeProvider) -> dict:
    from src.metals.pipeline import _fetch

    return _fetch(provider)


class TestComputeMetals:
    def test_all_ok(self) -> None:
        out = compute_metals(_closes(FakeProvider()))
        g = out['gold_silver_ratio']
        assert g['value'] is not None and g['value'] > 0
        assert g['percentile_5y'] is not None and 0.0 <= g['percentile_5y'] <= 1.0
        assert len(g['series']) == 252
        assert out['as_of'] == g['series'][-1][0]
        assert out['dxy']['r_20d'] is not None
        assert out['real_rate']['corr_gold_20d'] is not None
        assert abs(out['real_rate']['corr_gold_20d']) <= 1.0
        assert out['miner_leverage']['percentile_1y'] is not None
        assert set(out['source_status'].values()) == {'ok'}

    def test_aux_missing_degrades_not_raises(self) -> None:
        out = compute_metals(_closes(FakeProvider(fail={'TIP', 'DX-Y.NYB', 'GDX'})))
        assert out['source_status']['gold_silver'] == 'ok'
        assert out['source_status']['real_rate'] == 'missing'
        assert out['source_status']['dxy'] == 'missing'
        assert out['source_status']['miner_leverage'] == 'missing'
        assert out['real_rate']['tip_price'] is None
        assert out['dxy']['value'] is None

    def test_core_missing_raises(self) -> None:
        with pytest.raises(Exception, match='gold_silver'):
            compute_metals(_closes(FakeProvider(fail={'SLV'})))

    def test_nan_never_leaks_into_json(self) -> None:
        out = compute_metals(_closes(FakeProvider()))
        # corr 为 nan 的构造场景难造, 这里至少保证序列化不含 NaN 字面量
        text = json.dumps(out)
        assert 'NaN' not in text

    def test_gdx_no_overlap_degrades(self) -> None:
        provider = FakeProvider()
        closes = _closes(provider)
        # GDX 存在但日期与 GLD/SLV 完全不重叠
        _xd, xp = closes['GDX']
        shifted = pd.bdate_range('2031-01-01', periods=N)
        closes['GDX'] = ([d.strftime('%Y-%m-%d') for d in shifted], xp)
        out = compute_metals(closes)
        assert out['source_status']['miner_leverage'] == 'missing'
        assert out['miner_leverage']['ratio'] is None

    def test_tip_short_overlap_degrades(self) -> None:
        provider = FakeProvider()
        closes = _closes(provider)
        # TIP 只保留末尾 5 个日期, 重叠不足以算 20 日相关
        td, tp = closes['TIP']
        closes['TIP'] = (td[-5:], tp[-5:])
        out = compute_metals(closes)
        assert out['source_status']['real_rate'] == 'missing'
        assert out['real_rate']['tip_price'] is None


class TestRun:
    def test_run_writes_file_and_cn_side(self, tmp_path: Path) -> None:
        (tmp_path / 'latest').mkdir()
        (tmp_path / 'latest' / 'etfs.json').write_text(json.dumps({
            'schema_version': '1.1', 'generated_at': 'x',
            'etfs': [
                {'code': '518880', 'name': '黄金ETF', 'price': 7.5,
                 'returns': {'r_1d': 0.01}, 'amount_yi': 20.0},
                {'code': '161226', 'name': '白银LOF', 'price': 4.2,
                 'returns': {'r_1d': -0.005}, 'amount_yi': 1.5},
            ],
        }), encoding='utf-8')
        out = run(tmp_path, provider=FakeProvider())
        assert out.name == 'metals.json'
        data = json.loads(out.read_text(encoding='utf-8'))
        assert data['schema_version'] == '1.0'
        assert data['cn_side']['gold_etf']['code'] == '518880'
        assert data['cn_side']['silver_lof']['name'] == '白银LOF'
        assert data['cn_side']['silver_lof']['premium_pct'] is None
        assert data['source_status']['cn_side'] == 'ok'

    def test_cn_side_missing_etfs_json(self, tmp_path: Path) -> None:
        (tmp_path / 'latest').mkdir()
        out = run(tmp_path, provider=FakeProvider())
        data = json.loads(out.read_text(encoding='utf-8'))
        assert data['cn_side'] == {'gold_etf': None, 'silver_lof': None}
        assert data['source_status']['cn_side'] == 'missing'

    def test_generated_at_parses(self, tmp_path: Path) -> None:
        (tmp_path / 'latest').mkdir()
        run(tmp_path, provider=FakeProvider())
        data = json.loads((tmp_path / 'latest' / 'metals.json').read_text(encoding='utf-8'))
        datetime.fromisoformat(data['generated_at'])  # BJT iso 带时区

    def test_cn_side_codes_absent(self, tmp_path: Path) -> None:
        (tmp_path / 'latest').mkdir()
        (tmp_path / 'latest' / 'etfs.json').write_text(json.dumps({
            'schema_version': '1.1', 'generated_at': 'x', 'etfs': [
                {'code': '512480', 'name': '半导体ETF', 'price': 1.1, 'returns': {}, 'amount_yi': 1.0},
            ],
        }), encoding='utf-8')
        out = run(tmp_path, provider=FakeProvider())
        data = json.loads(out.read_text(encoding='utf-8'))
        assert data['cn_side'] == {'gold_etf': None, 'silver_lof': None}
        assert data['source_status']['cn_side'] == 'missing'


def test_main_writes_default_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.metals import pipeline as mp

    (tmp_path / 'latest').mkdir()
    monkeypatch.setattr(sys, 'argv', ['metals', f'--data-root={tmp_path}'])
    monkeypatch.setattr(mp, 'run', lambda root, provider=None: run(root, provider=FakeProvider()))
    mp.main()
    assert (tmp_path / 'latest' / 'metals.json').exists()
