"""snapshots_index 模块单测"""
import json
import tempfile
from pathlib import Path

from src.output.snapshots_index import build_snapshots_index, write_snapshots_index


def _touch_snapshot(snap_root: Path, date_str: str) -> None:
    d = snap_root / date_str
    d.mkdir(parents=True, exist_ok=True)
    (d / 'themes.json').write_text('{}', encoding='utf-8')


def test_build_index_returns_sorted_dates():
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        snap_root = data_root / 'snapshots'
        _touch_snapshot(snap_root, '2026-06-15')
        _touch_snapshot(snap_root, '2026-04-01')
        _touch_snapshot(snap_root, '2026-05-10')

        idx = build_snapshots_index(data_root)

        assert idx['schema_version'] == '1.0'
        assert 'generated_at' in idx
        dates = [s['date'] for s in idx['snapshots']]
        assert dates == ['2026-04-01', '2026-05-10', '2026-06-15']
        # themes_path 是相对 data_root 的相对路径 (POSIX 风格)
        assert idx['snapshots'][0]['themes_path'] == 'snapshots/2026-04-01/themes.json'


def test_build_index_skips_invalid_dirs():
    """非日期格式的目录 / 缺 themes.json 的目录 应被跳过"""
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        snap_root = data_root / 'snapshots'
        _touch_snapshot(snap_root, '2026-06-15')
        # 无 themes.json 的目录
        (snap_root / '2026-06-16').mkdir(parents=True)
        # 非日期格式的目录
        (snap_root / 'not-a-date').mkdir(parents=True)
        (snap_root / 'not-a-date' / 'themes.json').write_text('{}', encoding='utf-8')

        idx = build_snapshots_index(data_root)
        dates = [s['date'] for s in idx['snapshots']]
        assert dates == ['2026-06-15']


def test_build_index_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        (data_root / 'snapshots').mkdir(parents=True)
        idx = build_snapshots_index(data_root)
        assert idx['snapshots'] == []


def test_build_index_missing_snapshots_dir():
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        idx = build_snapshots_index(data_root)
        assert idx['snapshots'] == []


def test_write_snapshots_index_writes_file():
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        snap_root = data_root / 'snapshots'
        _touch_snapshot(snap_root, '2026-06-15')

        write_snapshots_index(data_root)

        path = data_root / 'latest' / 'snapshots-index.json'
        assert path.exists()
        idx = json.loads(path.read_text(encoding='utf-8'))
        assert idx['snapshots'][0]['date'] == '2026-06-15'
