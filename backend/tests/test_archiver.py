import tempfile
from datetime import date
from pathlib import Path

from src.output.archiver import archive_latest


def test_archive_copies_latest_to_dated_dir() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        latest = root / 'latest'
        latest.mkdir()
        (latest / 'themes.json').write_text('{"a":1}', encoding='utf-8')
        (latest / 'etfs.json').write_text('{}', encoding='utf-8')
        (latest / 'signals.json').write_text('{}', encoding='utf-8')
        (latest / 'meta.json').write_text('{}', encoding='utf-8')

        archive_latest(root, date(2026, 6, 5))

        archived = root / 'snapshots' / '2026-06-05'
        assert (archived / 'themes.json').read_text(encoding='utf-8') == '{"a":1}'
        assert (archived / 'etfs.json').exists()
        assert (archived / 'signals.json').exists()
        assert (archived / 'meta.json').exists()


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
