"""run_archive 契约: 归档 + 重建 snapshots-index 必须同步发生.

历史 bug: pipeline ARCHIVE 模式只写 snapshots/<date>/ 但不更新 latest/snapshots-index.json,
导致前端时光机永远看不到新归档. 本测试守护该回归.
"""
import json
import tempfile
from datetime import date
from pathlib import Path

from src.pipeline import run_archive


def _seed_latest(root: Path) -> None:
    latest = root / 'latest'
    latest.mkdir(parents=True, exist_ok=True)
    for name in ('themes.json', 'etfs.json', 'signals.json', 'meta.json'):
        (latest / name).write_text('{}', encoding='utf-8')


def test_run_archive_writes_snapshot_and_updates_index() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root)

        idx_path = run_archive(root, date(2026, 6, 22))

        # 1. 归档目录就位
        snap = root / 'snapshots' / '2026-06-22'
        assert (snap / 'themes.json').exists()

        # 2. index 写到了 latest/ 且包含新日期
        assert idx_path == root / 'latest' / 'snapshots-index.json'
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        dates = [s['date'] for s in idx['snapshots']]
        assert '2026-06-22' in dates


def test_run_archive_index_includes_preexisting_snapshots() -> None:
    """index 必须是全量重建, 不能只追加 — 否则 backfill 历史数据会被覆盖丢失."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root)
        # 预置一个旧快照 (模拟 backfill 产物)
        old = root / 'snapshots' / '2026-06-18'
        old.mkdir(parents=True)
        (old / 'themes.json').write_text('{}', encoding='utf-8')

        run_archive(root, date(2026, 6, 22))

        idx = json.loads((root / 'latest' / 'snapshots-index.json').read_text(encoding='utf-8'))
        dates = sorted(s['date'] for s in idx['snapshots'])
        assert dates == ['2026-06-18', '2026-06-22']
