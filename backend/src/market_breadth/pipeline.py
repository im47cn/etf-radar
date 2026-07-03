"""市场宽度计算管线: dapanyuntu 原始数据 -> market_temperature.json.

产出同时含二级原始值 / 一级聚合值 / 全市场均值序列.

口径 (与 prd 硬约束一致):
- value<=0 视为无数据, 一律过滤, 缺失日以 null 占位 (不当 0% 参与均值).
- 一级行业值 = 其下二级有效值的等权算术平均, 保留 1 位小数.
- 全市场值 = 当日所有二级有效值的等权算术平均 (数据源无成分股数, 无法个股加权).
- 行业按最新有值日期的值降序排列.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..output.writer import atomic_write_json
from ..providers.dapanyuntu_provider import BreadthRaw, DapanyuntuProvider
from .industry_mapping import OTHER_L1, to_l1

log = logging.getLogger(__name__)
BJT = ZoneInfo('Asia/Shanghai')

SCHEMA_VERSION = '1.0'


def _round1(x: float) -> float:
    return round(x, 1)


def _series_latest(series: list[float | None]) -> float | None:
    """series 最后一个非 null 值."""
    for v in reversed(series):
        if v is not None:
            return v
    return None


def _sort_by_latest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 latest 降序; latest 为 None 的排末尾."""
    return sorted(rows, key=lambda r: (r['latest'] is not None, r['latest'] or 0.0), reverse=True)


def compute_market_temperature(raw: BreadthRaw) -> dict[str, Any]:
    """把 dapanyuntu 稀疏三元组聚合为市场温度快照 dict."""
    dates = list(raw.dates)
    industries = list(raw.industries)
    n_dates = len(dates)

    # (industry_idx, date_idx) -> value, 已过滤 <=0
    grid: dict[tuple[int, int], float] = {}
    for triple in raw.data:
        di, ii, val = int(triple[0]), int(triple[1]), float(triple[2])
        if val <= 0:
            continue
        if 0 <= di < n_dates and 0 <= ii < len(industries):
            grid[(ii, di)] = val

    # 二级行业序列
    l2_rows: list[dict[str, Any]] = []
    unknown: set[str] = set()
    for ii, name in enumerate(industries):
        series: list[float | None] = [grid.get((ii, di)) for di in range(n_dates)]
        l1 = to_l1(name)
        l2_rows.append({'name': name, 'l1': l1, 'series': series, 'latest': _series_latest(series)})
        if l1 == OTHER_L1:
            unknown.add(name)
    if unknown:
        log.warning('dapanyuntu 未知二级行业(归入%s): %s', OTHER_L1, sorted(unknown))

    # 一级行业: 每个 (l1, date) 收集其下二级有效值取等权均值
    l1_bucket: dict[str, list[list[float]]] = defaultdict(lambda: [[] for _ in range(n_dates)])
    for ii, name in enumerate(industries):
        l1 = to_l1(name)
        for di in range(n_dates):
            v = grid.get((ii, di))
            if v is not None:
                l1_bucket[l1][di].append(v)
    l1_rows: list[dict[str, Any]] = []
    for l1, per_date in l1_bucket.items():
        series = [(_round1(sum(vs) / len(vs)) if vs else None) for vs in per_date]
        l1_rows.append({'name': l1, 'series': series, 'latest': _series_latest(series)})

    # 全市场: 当日所有二级有效值等权均值
    market: list[dict[str, Any]] = []
    for di in range(n_dates):
        day_vals = [grid[(ii, di)] for ii in range(len(industries)) if (ii, di) in grid]
        rate = _round1(sum(day_vals) / len(day_vals)) if day_vals else None
        market.append({'date': dates[di], 'rate': rate})

    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).astimezone(BJT).isoformat(),
        'source': 'dapanyuntu',
        'metric': 'ma20_above_ratio',
        'dates': dates,
        'market': market,
        'industries_l1': _sort_by_latest(l1_rows),
        'industries_l2': _sort_by_latest(l2_rows),
    }


def run(data_root: Path, provider: DapanyuntuProvider | None = None) -> Path:
    """拉取 -> 计算 -> 写 data_root/latest/market_temperature.json."""
    provider = provider or DapanyuntuProvider()
    raw = provider.fetch_breadth()
    snapshot = compute_market_temperature(raw)
    # 自建多周期宽度上线后, market_temperature.json 由 self_breadth 产出;
    # dapanyuntu 降级为 QC 对账源, 单写 qc 文件.
    out = Path(data_root) / 'latest' / 'market_breadth_qc_dapanyuntu.json'
    atomic_write_json(out, snapshot)
    log.info('dapanyuntu QC written: %d dates, %d L1, %d L2',
             len(snapshot['dates']), len(snapshot['industries_l1']), len(snapshot['industries_l2']))
    return out


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    parser = argparse.ArgumentParser(description='市场温度 (MA20 宽度) 管线')
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    run(args.data_root)


if __name__ == '__main__':
    main()
