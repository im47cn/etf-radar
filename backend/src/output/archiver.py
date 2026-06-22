"""EOD 归档 — 把 data/latest/ 复制到 data/snapshots/<YYYY-MM-DD>/."""
import shutil
from datetime import date
from pathlib import Path

from .snapshots_index import write_snapshots_index

FILES = ['themes.json', 'etfs.json', 'signals.json', 'meta.json']


def archive_latest(data_root: Path, target_date: date) -> Path:
    """归档 latest/ 至 snapshots/<YYYY-MM-DD>/ 并重建 snapshots-index.json.

    Args:
        data_root: 包含 latest/ 和 snapshots/ 的根目录
        target_date: 目标日期 (BJT, 由调用方决定时区)

    Returns:
        归档目录的 Path

    不变量: 写完 snapshots/<date>/ 必须重建 latest/snapshots-index.json,
    否则前端时光机看不到新归档. 该 reindex 内化在本函数中, 调用方无需关心.
    (历史 bug: pipeline 层手动组合 archive + reindex 时遗漏了 reindex.)
    """
    data_root = Path(data_root)
    src = data_root / 'latest'
    dst = data_root / 'snapshots' / target_date.strftime('%Y-%m-%d')
    dst.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)
    # 原子约束: 任何对 snapshots/ 的修改都必须同步重建 index
    write_snapshots_index(data_root)
    return dst
