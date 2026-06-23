"""验证 data/holdings/*.json 与 stocks_spot.json 符合 schema。"""
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOLDINGS_DIR = REPO_ROOT / 'data' / 'holdings'
LATEST_DIR = REPO_ROOT / 'data' / 'latest'


def _iter_etf_files() -> list[Path]:
    if not HOLDINGS_DIR.exists():
        return []
    return [p for p in HOLDINGS_DIR.glob('*.json') if p.name != 'index.json']


@pytest.mark.skipif(not HOLDINGS_DIR.exists(), reason='holdings not yet seeded')
def test_each_etf_json_has_required_fields():
    for path in _iter_etf_files():
        data = json.loads(path.read_text(encoding='utf-8'))
        assert {'etf_code', 'etf_name', 'disclosure_date',
                'fetched_at', 'top_holdings'} <= set(data.keys()), path.name
        assert isinstance(data['top_holdings'], list)
        assert len(data['top_holdings']) <= 10


@pytest.mark.skipif(not HOLDINGS_DIR.exists(), reason='holdings not yet seeded')
def test_each_holding_weight_in_range():
    for path in _iter_etf_files():
        data = json.loads(path.read_text(encoding='utf-8'))
        for h in data['top_holdings']:
            assert 0 <= h['weight'] <= 100, f"{path.name}: {h}"
            assert h['code'] and h['name']


@pytest.mark.skipif(not (HOLDINGS_DIR / 'index.json').exists(),
                    reason='index not yet generated')
def test_index_lists_only_existing_files():
    index = json.loads((HOLDINGS_DIR / 'index.json').read_text(encoding='utf-8'))
    for entry in index['etfs']:
        assert (HOLDINGS_DIR / f"{entry['code']}.json").exists()


@pytest.mark.skipif(not (LATEST_DIR / 'stocks_spot.json').exists(),
                    reason='stocks_spot not yet generated')
def test_stocks_spot_schema():
    data = json.loads((LATEST_DIR / 'stocks_spot.json').read_text(encoding='utf-8'))
    assert data['schema_version'] == '1.0'
    assert 'stocks' in data
    for code, spot in data['stocks'].items():
        assert isinstance(code, str)
        assert isinstance(spot['name'], str)
        assert isinstance(spot['close'], (int, float))
        assert spot['r_1d'] is None or isinstance(spot['r_1d'], (int, float))
