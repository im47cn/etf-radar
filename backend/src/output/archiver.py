"""EOD 归档 — 把 data/latest/ 复制到 data/snapshots/<YYYY-MM-DD>/."""
import shutil
from datetime import date
from pathlib import Path

FILES = ['themes.json', 'etfs.json', 'signals.json', 'meta.json']


def archive_latest(data_root: Path, target_date: date) -> Path:
    """Copy latest/ snapshot to snapshots/<YYYY-MM-DD>/.

    Args:
        data_root: 包含 latest/ 和 snapshots/ 的根目录
        target_date: 目标日期 (BJT, 由调用方决定时区)

    Returns:
        归档目录的 Path
    """
    data_root = Path(data_root)
    src = data_root / 'latest'
    dst = data_root / 'snapshots' / target_date.strftime('%Y-%m-%d')
    dst.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)
    return dst
