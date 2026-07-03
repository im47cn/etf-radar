"""自建个股宽度计算 (纯函数): close_series + 巨潮行业映射 → 多周期宽度快照(schema 2.0).

口径:
- 站上判定: close[i] > SMA_n(该股最近 n 个有效收盘)。
- 有效样本: 该股当日 close 非 null 且已累计 ≥n 个有效收盘。分母只含有效样本。
- 全市场 = 全体有效个股占比 (真·个股占比); 二级/一级按巨潮中类/大类分组直接个股级聚合。
- 无行业归属个股计入全市场, 不计入任何行业。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..output.writer import atomic_write_json
from .pipeline import _series_latest, _sort_by_latest

BJT = ZoneInfo('Asia/Shanghai')
SCHEMA_VERSION = '2.0'
DEFAULT_PERIODS = (20, 60, 120)


def _rate(above: int, valid: int) -> float | None:
    return round(above / valid * 100, 1) if valid > 0 else None


def _rows_from(
    above: dict[str, list[int]], valid: dict[str, list[int]], dates: list[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    n = len(dates)
    for name in above:
        series = [_rate(above[name][i], valid[name][i]) for i in range(n)]
        rows.append({'name': name, 'series': series, 'latest': _series_latest(series)})
    return _sort_by_latest(rows)


def _period_breadth(
    stocks: dict[str, list[float | None]],
    industry_map: dict[str, dict[str, str]],
    n_dates: int,
    period: int,
) -> dict[str, Any]:
    mkt_valid = [0] * n_dates
    mkt_above = [0] * n_dates
    l1_valid: dict[str, list[int]] = defaultdict(lambda: [0] * n_dates)
    l1_above: dict[str, list[int]] = defaultdict(lambda: [0] * n_dates)
    l2_valid: dict[str, list[int]] = defaultdict(lambda: [0] * n_dates)
    l2_above: dict[str, list[int]] = defaultdict(lambda: [0] * n_dates)

    for code, closes in stocks.items():
        # 非 null 收盘 + 原始日期下标
        idx: list[int] = []
        vals: list[float] = []
        for i, c in enumerate(closes):
            if c is not None:
                idx.append(i)
                vals.append(c)
        if len(vals) < period:
            continue
        # 前缀和滚动均值
        pref = [0.0]
        for v in vals:
            pref.append(pref[-1] + v)
        ind = industry_map.get(code)
        l1 = ind['l1'] if ind else None
        l2 = ind['l2'] if ind else None
        for p in range(period - 1, len(vals)):
            day = idx[p]
            sma = (pref[p + 1] - pref[p + 1 - period]) / period
            above = 1 if vals[p] > sma else 0
            mkt_valid[day] += 1
            mkt_above[day] += above
            if l1 is not None:
                l1_valid[l1][day] += 1
                l1_above[l1][day] += above
            if l2 is not None:
                l2_valid[l2][day] += 1
                l2_above[l2][day] += above

    return {
        'mkt_valid': mkt_valid,
        'mkt_above': mkt_above,
        'l1': (l1_above, l1_valid),
        'l2': (l2_above, l2_valid),
    }


def compute_self_breadth(
    close_series: dict[str, Any],
    industry_map: dict[str, dict[str, str]],
    periods: tuple[int, ...] = DEFAULT_PERIODS,
) -> dict[str, Any]:
    dates: list[str] = list(close_series['dates'])
    stocks: dict[str, list[float | None]] = close_series['stocks']
    n_dates = len(dates)

    out_periods: dict[str, Any] = {}
    for period in periods:
        acc = _period_breadth(stocks, industry_map, n_dates, period)
        market = [
            {'date': dates[i], 'rate': _rate(acc['mkt_above'][i], acc['mkt_valid'][i])}
            for i in range(n_dates)
        ]
        l1_above, l1_valid = acc['l1']
        l2_above, l2_valid = acc['l2']
        out_periods[f'ma{period}'] = {
            'market': market,
            'industries_l1': _rows_from(l1_above, l1_valid, dates),
            'industries_l2': _rows_from(l2_above, l2_valid, dates),
        }

    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).astimezone(BJT).isoformat(),
        'source': 'self',
        'metric': 'maN_above_ratio',
        'dates': dates,
        'periods': out_periods,
    }


def run(data_root: Path, periods: tuple[int, ...] = DEFAULT_PERIODS) -> Path:
    import json

    stocks_dir = Path(data_root) / 'stocks'
    close_series = json.loads((stocks_dir / 'close_series.json').read_text(encoding='utf-8'))
    map_path = stocks_dir / 'stock_industry_map.json'
    industry_map = json.loads(map_path.read_text(encoding='utf-8'))['map'] if map_path.exists() else {}

    snapshot = compute_self_breadth(close_series, industry_map, periods)
    out = Path(data_root) / 'latest' / 'market_temperature.json'
    atomic_write_json(out, snapshot)
    return out


def main() -> None:
    import argparse
    import logging

    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description='自建个股宽度多周期管线')
    p.add_argument('--data-root', type=Path, default=Path('data'))
    args = p.parse_args()
    run(args.data_root)


if __name__ == '__main__':
    main()
