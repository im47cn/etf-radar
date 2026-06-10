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
