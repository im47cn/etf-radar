"""扫 data/snapshots/ 生成 latest/snapshots-index.json"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .writer import atomic_write_json

BJT = ZoneInfo('Asia/Shanghai')
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def build_snapshots_index(data_root: Path) -> dict[str, Any]:
    """扫 data_root/snapshots/<YYYY-MM-DD>/ 目录, 返回索引 dict.

    只收录目录名匹配 YYYY-MM-DD 且包含 themes.json 的快照。
    entry 的 trading_path 为条件键: 仅快照目录含 trading.json 时出现 (旧快照无此键)。
    """
    snap_root = data_root / 'snapshots'
    snapshots: list[dict[str, str]] = []
    if snap_root.exists():
        for d in sorted(snap_root.iterdir()):
            if not d.is_dir():
                continue
            if not _DATE_RE.match(d.name):
                continue
            try:
                datetime.strptime(d.name, '%Y-%m-%d')  # noqa: DTZ007  仅校验目录名格式
            except ValueError:
                continue
            if not (d / 'themes.json').exists():
                continue
            entry: dict[str, str] = {
                'date': d.name,
                'themes_path': f'snapshots/{d.name}/themes.json',
            }
            if (d / 'trading.json').exists():
                entry['trading_path'] = f'snapshots/{d.name}/trading.json'
            snapshots.append(entry)

    return {
        'schema_version': '1.0',
        'generated_at': datetime.now(UTC).astimezone(BJT).isoformat(),
        'snapshots': snapshots,
    }


def write_snapshots_index(data_root: Path) -> Path:
    idx = build_snapshots_index(data_root)
    out = data_root / 'latest' / 'snapshots-index.json'
    atomic_write_json(out, idx)
    return out
