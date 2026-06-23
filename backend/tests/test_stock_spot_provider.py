"""stock_spot_provider 测试 (mock akshare)"""
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.providers.stock_spot_provider import (
    build_stocks_spot_payload,
    collect_holdings_codes,
    write_stocks_spot_snapshot,
)


@pytest.fixture
def fake_spot_df():
    """模拟 ak.stock_zh_a_spot_em 返回的全市场 DataFrame。"""
    return pd.DataFrame({
        '代码': ['002129', '603501', '999999'],
        '名称': ['TCL中环', '韦尔股份', '不相关'],
        '最新价': [12.5, 98.7, 33.0],
        '涨跌幅': [2.5, -1.2, 0.0],   # akshare 返回的是百分比单位 (%)
    })


def test_collect_holdings_codes(tmp_path: Path):
    (tmp_path / 'a.json').write_text(json.dumps({
        'etf_code': '512480', 'etf_name': 'x',
        'disclosure_date': '2026-03-31', 'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [
            {'code': '002129', 'name': 'TCL中环', 'weight': 8.5},
            {'code': '603501', 'name': '韦尔股份', 'weight': 7.2},
        ],
    }), encoding='utf-8')
    (tmp_path / 'b.json').write_text(json.dumps({
        'etf_code': '159870', 'etf_name': 'y',
        'disclosure_date': '2026-03-31', 'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [
            {'code': '002129', 'name': 'TCL中环', 'weight': 5.0},
        ],
    }), encoding='utf-8')
    (tmp_path / 'index.json').write_text('{}', encoding='utf-8')

    codes = collect_holdings_codes(tmp_path)
    assert codes == {'002129', '603501'}  # index.json 被忽略，去重


def test_build_payload_filters_by_codes(fake_spot_df):
    payload = build_stocks_spot_payload(fake_spot_df, target_codes={'002129', '603501'})
    assert set(payload['stocks'].keys()) == {'002129', '603501'}
    assert payload['stocks']['002129']['close'] == 12.5
    assert payload['stocks']['002129']['r_1d'] == pytest.approx(0.025)  # 2.5% → 0.025
    assert payload['stocks']['603501']['r_1d'] == pytest.approx(-0.012)


def test_build_payload_handles_missing_pct():
    df = pd.DataFrame({
        '代码': ['002129'], '名称': ['x'], '最新价': [12.5],
        '涨跌幅': [None],
    })
    payload = build_stocks_spot_payload(df, target_codes={'002129'})
    assert payload['stocks']['002129']['r_1d'] is None


def test_write_snapshot_creates_file(tmp_path, fake_spot_df):
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / '512480.json').write_text(json.dumps({
        'etf_code': '512480', 'etf_name': 'x',
        'disclosure_date': '2026-03-31', 'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'x', 'weight': 5.0}],
    }), encoding='utf-8')

    out_path = tmp_path / 'latest' / 'stocks_spot.json'
    out_path.parent.mkdir()

    with patch('src.providers.stock_spot_provider.ak.stock_zh_a_spot_em',
               return_value=fake_spot_df):
        write_stocks_spot_snapshot(out_path=out_path, holdings_dir=holdings_dir)

    data = json.loads(out_path.read_text())
    assert '002129' in data['stocks']


def test_write_snapshot_fallback_on_akshare_failure(tmp_path):
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    out_path = tmp_path / 'latest' / 'stocks_spot.json'
    out_path.parent.mkdir()

    with patch('src.providers.stock_spot_provider.ak.stock_zh_a_spot_em',
               side_effect=Exception('network')):
        write_stocks_spot_snapshot(out_path=out_path, holdings_dir=holdings_dir)

    data = json.loads(out_path.read_text())
    assert data['stocks'] == {}
