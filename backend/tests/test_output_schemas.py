"""JSON Schema validation for pipeline output files.

如果 data/latest/<name>.json 尚未 bootstrap, 测试自动 SKIP (不阻塞 CI)。
"""
import json
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

ROOT = Path(__file__).parent.parent.parent  # repo root
SCHEMAS = Path(__file__).parent / 'schemas'
LATEST = ROOT / 'data' / 'latest'


@pytest.mark.parametrize('name', ['themes', 'etfs', 'signals', 'meta'])
def test_latest_matches_schema(name: str) -> None:
    schema_file = SCHEMAS / f'{name}.schema.json'
    data_file = LATEST / f'{name}.json'
    if not data_file.exists():
        pytest.skip(f'{data_file} not yet bootstrapped')
    schema = json.loads(schema_file.read_text(encoding='utf-8'))
    data = json.loads(data_file.read_text(encoding='utf-8'))
    jsonschema.validate(data, schema)


def test_all_4_schemas_loadable() -> None:
    """4 个 schema 文件本身必须是合法 JSON Schema (即使 data 没生成也跑这个)."""
    from jsonschema import Draft7Validator
    for name in ['themes', 'etfs', 'signals', 'meta']:
        schema = json.loads((SCHEMAS / f'{name}.schema.json').read_text(encoding='utf-8'))
        Draft7Validator.check_schema(schema)


# ---------------------------------------------------------------------------
# themes.schema.json v1.1 专项测试
# ---------------------------------------------------------------------------
from jsonschema import validate, Draft7Validator


def _schema():
    return json.loads((SCHEMAS / 'themes.schema.json').read_text(encoding='utf-8'))


def test_themes_schema_version_is_1_1():
    s = _schema()
    assert s['properties']['schema_version']['const'] == '1.1'


def test_themes_schema_validates_cn_only_entry():
    doc = {
        'schema_version': '1.1',
        'generated_at': '2025-06-19T16:00:00+08:00',
        'themes': [{
            'id': 'cn_x', 'name': 'X',
            'us_etfs': [], 'primary_us': None, 'primary_cn': '000001',
            'tags': [], 'note': '',
            'returns': {'r_1d': None, 'r_5d': None, 'r_20d': None,
                        'r_60d': None, 'r_120d': None, 'r_ytd': None},
            'strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'us_strength': None,
            'cn_strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'rank': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
        }],
    }
    validate(instance=doc, schema=_schema())


def test_themes_schema_validates_mapped_entry():
    doc = {
        'schema_version': '1.1',
        'generated_at': '2025-06-19T16:00:00+08:00',
        'themes': [{
            'id': 'm', 'name': 'M',
            'us_etfs': ['SOXX'], 'primary_us': 'SOXX', 'primary_cn': None,
            'tags': [], 'note': '',
            'returns': {'r_1d': None, 'r_5d': None, 'r_20d': None,
                        'r_60d': None, 'r_120d': None, 'r_ytd': None},
            'strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'us_strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'cn_strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'rank': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
        }],
    }
    validate(instance=doc, schema=_schema())
