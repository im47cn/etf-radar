"""删除 data/snapshots/ 下 >2 年 (730 天) 的归档目录。

用法:
    python scripts/archive_cleanup.py
"""
import shutil
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
SNAPS = ROOT / 'data' / 'snapshots'


def main(retention_days: int = 730) -> None:
    if not SNAPS.exists():
        print('No snapshots dir, nothing to clean')
        return
    cutoff = date.today() - timedelta(days=retention_days)
    removed = 0
    for sub in SNAPS.iterdir():
        if not sub.is_dir():
            continue
        try:
            d = date.fromisoformat(sub.name)
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(sub)
            removed += 1
            print(f'removed {sub}')
    print(f'cleaned {removed} old snapshots (cutoff: {cutoff})')


if __name__ == '__main__':
    main()
