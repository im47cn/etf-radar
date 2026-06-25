"""daily pipeline: 追加今日 spot → 算 indicators → 写文件"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.stocks_daily_pipeline import run_daily_pipeline


def _make_close_series(codes: list[str], n_days: int = 75) -> dict:
    dates = [f'2026-04-{i+1:02d}' for i in range(n_days)]
    return {
        'schema_version': '1.0',
        'generated_at': '2026-04-30T00:00:00+00:00',
        'dates': dates,
        'stocks': {code: [10.0 + i * 0.01 for i in range(n_days)] for code in codes},
    }


def _make_volume_series(codes: list[str], n_days: int = 75) -> dict:
    dates = [f'2026-04-{i+1:02d}' for i in range(n_days)]
    return {
        'schema_version': '1.0',
        'generated_at': '2026-04-30T00:00:00+00:00',
        'dates': dates,
        'stocks': {code: [1000000 + i * 1000 for i in range(n_days)] for code in codes},
    }


def _fake_spot_df(codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        '代码': codes,
        '名称': [f'股{c}' for c in codes],
        '最新价': [11.0 for _ in codes],
        '成交量': [2000000 for _ in codes],
    })


def test_daily_appends_today_and_writes_indicators(tmp_path: Path):
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / 'a.json').write_text(json.dumps({
        'etf_code': 'a', 'etf_name': 'a', 'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'TCL中环', 'weight': 8.5}],
    }))

    out_dir = tmp_path / 'stocks'
    out_dir.mkdir()
    (out_dir / 'ohlc').mkdir()
    universe_codes = ['002129', '603501', '600519']
    (out_dir / 'close_series.json').write_text(json.dumps(_make_close_series(universe_codes)))
    (out_dir / 'volume_series.json').write_text(json.dumps(_make_volume_series(universe_codes)))

    with patch('src.stocks_daily_pipeline._fetch_today_spot',
               return_value=_fake_spot_df(universe_codes)):
        run_daily_pipeline(
            holdings_dir=holdings_dir, out_dir=out_dir, today=date(2026, 6, 25),
        )

    cs = json.loads((out_dir / 'close_series.json').read_text())
    assert len(cs['dates']) == 75
    assert cs['dates'][-1] == '2026-06-25'
    assert cs['stocks']['002129'][-1] == 11.0

    hi = json.loads((out_dir / 'holdings_indicators.json').read_text())
    assert '002129' in hi['stocks']
    assert '603501' not in hi['stocks']
    ind = hi['stocks']['002129']
    assert 'strength_60d' in ind
    assert 'rsi_14' in ind
    assert 'vol_ratio' in ind
    assert 'leader' in ind


def test_daily_handles_spot_fetch_failure_keeps_existing(tmp_path: Path):
    """spot 拉不到 → 保留昨日 holdings_indicators，不写空文件覆盖"""
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / 'a.json').write_text(json.dumps({
        'etf_code': 'a', 'etf_name': 'a', 'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'x', 'weight': 1.0}],
    }))
    out_dir = tmp_path / 'stocks'
    out_dir.mkdir()
    (out_dir / 'ohlc').mkdir()
    (out_dir / 'close_series.json').write_text(json.dumps(_make_close_series(['002129'])))
    (out_dir / 'volume_series.json').write_text(json.dumps(_make_volume_series(['002129'])))

    existing = {'schema_version': '1.0', 'generated_at': 'old',
                'stocks': {'002129': {'name': 'x', 'strength_60d': 50,
                                       'strength_20d': 50, 'rsi_14': 50.0,
                                       'vol_ratio': 1.0, 'leader': ''}}}
    (out_dir / 'holdings_indicators.json').write_text(json.dumps(existing))

    with patch('src.stocks_daily_pipeline._fetch_today_spot',
               side_effect=RuntimeError('akshare down')):
        run_daily_pipeline(
            holdings_dir=holdings_dir, out_dir=out_dir, today=date(2026, 6, 25),
        )

    hi = json.loads((out_dir / 'holdings_indicators.json').read_text())
    assert hi['generated_at'] == 'old'


def test_daily_includes_leader_field(tmp_path: Path):
    """leader 字段必须存在且为合法值"""
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / 'a.json').write_text(json.dumps({
        'etf_code': 'a', 'etf_name': 'a', 'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'x', 'weight': 1.0}],
    }))
    out_dir = tmp_path / 'stocks'
    out_dir.mkdir()
    (out_dir / 'ohlc').mkdir()
    (out_dir / 'close_series.json').write_text(json.dumps(_make_close_series(['002129'])))
    (out_dir / 'volume_series.json').write_text(json.dumps(_make_volume_series(['002129'])))

    with patch('src.stocks_daily_pipeline._fetch_today_spot',
               return_value=_fake_spot_df(['002129'])):
        run_daily_pipeline(
            holdings_dir=holdings_dir, out_dir=out_dir, today=date(2026, 6, 25),
        )

    hi = json.loads((out_dir / 'holdings_indicators.json').read_text())
    leader = hi['stocks']['002129']['leader']
    assert leader in ('⭐⭐⭐', '⭐⭐', '⭐', '')
