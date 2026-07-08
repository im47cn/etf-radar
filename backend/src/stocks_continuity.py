"""close_series 内部交易日连续性检测(C4 self-heal 基石)。

纯函数 `missing_trading_days` 供 workflow 与 C1 哨兵复用;CLI 供 stocks-daily.yml
在 push 后自检,exit 3 表示存在缺口(区分于普通错误 exit!=0)。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from .etl.calendar import is_cn_trading_day

GAP_EXIT_CODE = 3  # C1 哨兵复用契约:3=有缺口


def missing_trading_days(dates: list[str], today: date | None = None) -> list[date]:
    """返回 close_series 内部按 chinese_calendar 应存在却缺失的交易日。

    只检测已有序列内部空洞(min(dates)..max(dates) 区间),不含未来。`today`
    参数保留供未来扩展(如检测"最新交易日缺失"),当前逻辑不使用。
    """
    if len(dates) < 2:
        return []
    parsed = sorted(date.fromisoformat(d) for d in dates)
    present = set(parsed)
    missing: list[date] = []
    cur = parsed[0] + timedelta(days=1)
    end = parsed[-1]
    while cur < end:
        if cur not in present and is_cn_trading_day(cur):
            missing.append(cur)
        cur += timedelta(days=1)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    close_path = args.data_root / 'stocks' / 'close_series.json'
    if not close_path.exists():
        print(f'close_series not found: {close_path}', file=sys.stderr)
        return 1
    data = json.loads(close_path.read_text(encoding='utf-8'))
    # close_series 损坏成非 dict(list/null)时不应崩溃, 视作空序列。
    raw_dates = data.get('dates', []) if isinstance(data, dict) else []
    dates: list[str] = raw_dates if isinstance(raw_dates, list) else []
    gaps = missing_trading_days(dates)
    if gaps:
        print(','.join(d.isoformat() for d in gaps))
        print(f'gap detected: {len(gaps)} missing trading day(s)', file=sys.stderr)
        return GAP_EXIT_CODE
    print(f'no gap: {len(dates)} dates continuous', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
