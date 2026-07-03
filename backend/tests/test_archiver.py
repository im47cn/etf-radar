import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.output.archiver import StaleDataError, archive_latest


def _seed_latest(root: Path, themes_content: str = '{"a":1}', meta: dict | None = None) -> None:
    latest = root / 'latest'
    latest.mkdir(parents=True, exist_ok=True)
    (latest / 'themes.json').write_text(themes_content, encoding='utf-8')
    (latest / 'etfs.json').write_text('{}', encoding='utf-8')
    (latest / 'signals.json').write_text('{}', encoding='utf-8')
    (latest / 'meta.json').write_text(json.dumps(meta or {}), encoding='utf-8')


def test_archive_copies_latest_to_dated_dir() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root)

        archive_latest(root, date(2026, 6, 5))

        archived = root / 'snapshots' / '2026-06-05'
        assert (archived / 'themes.json').read_text(encoding='utf-8') == '{"a":1}'
        assert (archived / 'etfs.json').exists()
        assert (archived / 'signals.json').exists()
        assert (archived / 'meta.json').exists()


def test_archive_copies_market_temperature_when_present() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root)
        (root / 'latest' / 'market_temperature.json').write_text('{"metric":"ma20"}', encoding='utf-8')

        archive_latest(root, date(2026, 6, 5))

        assert (root / 'snapshots' / '2026-06-05' / 'market_temperature.json').exists()


def test_archive_handles_missing_files() -> None:
    """latest/ 部分文件缺失时不应抛错, 只复制存在的"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        latest = root / 'latest'
        latest.mkdir()
        (latest / 'themes.json').write_text('{}', encoding='utf-8')
        # 故意只写一个

        dst = archive_latest(root, date(2026, 6, 5))

        assert (dst / 'themes.json').exists()
        assert not (dst / 'etfs.json').exists()


# --- 不变量: archive 必须重建 snapshots-index.json (防 archive-without-reindex 回归) ---


def test_archive_rebuilds_snapshots_index() -> None:
    """archive 完成后, latest/snapshots-index.json 必须包含新日期."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root)

        archive_latest(root, date(2026, 6, 22))

        idx_path = root / 'latest' / 'snapshots-index.json'
        assert idx_path.exists()
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        dates = [s['date'] for s in idx['snapshots']]
        assert '2026-06-22' in dates


def test_archive_index_includes_preexisting_snapshots() -> None:
    """index 是全量重建, 旧的 backfill 快照不能丢."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root)
        # 预置一个 backfill 历史快照
        old = root / 'snapshots' / '2026-06-18'
        old.mkdir(parents=True)
        (old / 'themes.json').write_text('{}', encoding='utf-8')

        archive_latest(root, date(2026, 6, 22))

        idx = json.loads((root / 'latest' / 'snapshots-index.json').read_text(encoding='utf-8'))
        dates = sorted(s['date'] for s in idx['snapshots'])
        assert dates == ['2026-06-18', '2026-06-22']


# --- 数据新鲜度护栏: 拒绝把陈旧 CN 数据归档成"今天"的快照 ---


def test_archive_refuses_stale_cn_data_on_trading_day() -> None:
    """CN 交易日但 cn_data_date != 目标日 → 拒绝归档 (不写快照)."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root, meta={
            'calendar': {'cn_trading_today': True},
            'cn_data_date': '2026-06-25',  # 陈旧: 目标是 06-26
        })

        with pytest.raises(StaleDataError):
            archive_latest(root, date(2026, 6, 26))

        # 不能写出陈旧快照
        assert not (root / 'snapshots' / '2026-06-26').exists()


def test_archive_allows_fresh_cn_data() -> None:
    """cn_data_date == 目标日 → 正常归档."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root, meta={
            'calendar': {'cn_trading_today': True},
            'cn_data_date': '2026-06-26',
        })

        archive_latest(root, date(2026, 6, 26))

        assert (root / 'snapshots' / '2026-06-26' / 'themes.json').exists()


def test_archive_skips_guard_when_not_cn_trading_day() -> None:
    """非 CN 交易日 (如美股单边日) 不校验 CN 新鲜度, 正常归档."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _seed_latest(root, meta={
            'calendar': {'cn_trading_today': False},
            'cn_data_date': '2026-06-25',
        })

        archive_latest(root, date(2026, 6, 26))

        assert (root / 'snapshots' / '2026-06-26' / 'themes.json').exists()
