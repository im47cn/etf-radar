"""EOD 归档 — 把 data/latest/ 复制到 data/snapshots/<YYYY-MM-DD>/."""
import json
import shutil
from datetime import date
from pathlib import Path

from .snapshots_index import write_snapshots_index

FILES = ['themes.json', 'etfs.json', 'signals.json', 'meta.json', 'market_temperature.json',
         'market_breadth_qc.json', 'market_breadth_qc_dapanyuntu.json']


class StaleDataError(Exception):
    """latest/ 数据非目标交易日, 拒绝归档以免陈旧数据污染快照历史."""


def _assert_fresh(src: Path, target_date: date) -> None:
    """数据新鲜度护栏: CN 交易日必须持有当日 bar 才允许归档.

    仅在能明确判定陈旧时拦截 (meta 标注 cn_trading_today 且 cn_data_date
    存在且 != 目标日); meta 缺字段 / 无法判定时放行, 保持向后兼容.
    """
    meta_path = src / 'meta.json'
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return
    calendar = meta.get('calendar') or {}
    cn_data_date = meta.get('cn_data_date')
    if (
        calendar.get('cn_trading_today')
        and cn_data_date
        and cn_data_date != target_date.isoformat()
    ):
        raise StaleDataError(
            f'CN data stale: cn_data_date={cn_data_date} != target={target_date.isoformat()}; '
            f'拒绝归档以免陈旧数据污染快照历史'
        )


def archive_latest(data_root: Path, target_date: date) -> Path:
    """归档 latest/ 至 snapshots/<YYYY-MM-DD>/ 并重建 snapshots-index.json.

    Args:
        data_root: 包含 latest/ 和 snapshots/ 的根目录
        target_date: 目标日期 (BJT, 由调用方决定时区)

    Returns:
        归档目录的 Path

    Raises:
        StaleDataError: latest/ 的 CN 数据非 target_date 当日 (见 _assert_fresh).

    不变量: 写完 snapshots/<date>/ 必须重建 latest/snapshots-index.json,
    否则前端时光机看不到新归档. 该 reindex 内化在本函数中, 调用方无需关心.
    (历史 bug: pipeline 层手动组合 archive + reindex 时遗漏了 reindex.)
    """
    data_root = Path(data_root)
    src = data_root / 'latest'
    _assert_fresh(src, target_date)
    dst = data_root / 'snapshots' / target_date.strftime('%Y-%m-%d')
    dst.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)
    # 原子约束: 任何对 snapshots/ 的修改都必须同步重建 index
    write_snapshots_index(data_root)
    return dst
