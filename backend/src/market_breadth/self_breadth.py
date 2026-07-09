"""自建个股宽度计算 (纯函数): close_series + 巨潮行业映射 → 多周期宽度快照(schema 2.0).

口径:
- 站上判定: close[i] > SMA_n(该股最近 n 个有效收盘)。
- 有效样本: 该股当日 close 非 null 且已累计 ≥n 个有效收盘。分母只含有效样本。
- 全市场 = 全体有效个股占比 (真·个股占比); 二级/一级按巨潮中类/大类分组直接个股级聚合。
- 无行业归属个股计入全市场, 不计入任何行业。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..etl.calendar import is_cn_trading_day
from ..output.writer import atomic_write_json
from .pipeline import _series_latest, _sort_by_latest

log = logging.getLogger(__name__)

BJT = ZoneInfo('Asia/Shanghai')
SCHEMA_VERSION = '2.0'
DEFAULT_PERIODS = (20, 60, 120)

# A 股 EOD 结算发布时点: 收盘后当日 bar 通常 18:00 BJT 前后才 roll 出.
# 与 pipeline.CN_SETTLE_HOUR 同源口径, 早于此时点不期望今日数据 (避免盘中误报陈旧).
CN_SETTLE_HOUR = 18
# 回溯最近已收盘交易日的最大自然日窗口:
# 覆盖春节 + 相邻周末最长闭市 (~16 自然日) 再加缓冲, 故取 21.
_ASOF_LOOKBACK_DAYS = 21


def _expected_breadth_asof(now_bjt: datetime) -> date:
    """期望的"最近已收盘 CN 交易日":判定温度链是否陈旧的基准日.

    - 今日为交易日且已过结算时点 (≥18:00) → 今日;
    - 否则 (盘中/结算前/非交易日) 回溯最近一个已收盘交易日.

    注意: 与 pipeline._expected_cn_date 语义相反 —— 那个盘中/非交易日返回 None
    (拿到啥用啥, 不判陈旧); 本函数必须返回一个基准日才能判 stale, 故独立命名.

    兜底: 若回溯 _ASOF_LOOKBACK_DAYS 天仍未命中交易日 (极端/日历数据缺失),
    返回回溯窗口内**最旧**的候选日 (today - N). 方向保守 —— 使 as_of 更易
    被判为 "达标/较新", 宁可漏报也不误报把近期数据错判为陈旧.
    """
    today = now_bjt.date()
    if is_cn_trading_day(today) and now_bjt.hour >= CN_SETTLE_HOUR:
        return today
    # 从昨日起回溯, 命中第一个交易日即为期望 as_of
    for delta in range(1, _ASOF_LOOKBACK_DAYS + 1):
        cand = today - timedelta(days=delta)
        if is_cn_trading_day(cand):
            return cand
    return today - timedelta(days=_ASOF_LOOKBACK_DAYS)


def _freshness(dates: list[str], now_bjt: datetime) -> dict[str, Any]:
    """温度链新鲜度判定 (纯函数, 便于测试).

    → {as_of: str|None, expected_date: str, stale: bool}
    stale = as_of < expected_date (按 date 解析后比较, 防御字符串序不一致).
    - dates 为空 → as_of=None, stale=False (不误报).
    - as_of 格式异常无法解析 → log.error 且 stale=False (保守不报).
    """
    expected = _expected_breadth_asof(now_bjt)
    expected_str = expected.isoformat()
    as_of = dates[-1] if dates else None
    if as_of is None:
        return {'as_of': None, 'expected_date': expected_str, 'stale': False}
    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError:
        log.error('malformed as_of date: %s', as_of)
        return {'as_of': as_of, 'expected_date': expected_str, 'stale': False}
    return {'as_of': as_of, 'expected_date': expected_str, 'stale': as_of_date < expected}


def _rate(above: int, valid: int) -> float | None:
    return round(above / valid * 100, 1) if valid > 0 else None


def _rows_from(
    above: dict[str, list[int]], valid: dict[str, list[int]], dates: list[str],
    parent: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    n = len(dates)
    for name in above:
        series = [_rate(above[name][i], valid[name][i]) for i in range(n)]
        row: dict[str, Any] = {'name': name, 'series': series, 'latest': _series_latest(series)}
        if parent is not None and name in parent:
            row['l1'] = parent[name]  # 二级行携带一级父级, 供前端折叠分组
        rows.append(row)
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
    l2_parent: dict[str, str] = {}  # 大类(l2) -> 门类(l1)

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
        if l2 is not None and l1 is not None:
            l2_parent[l2] = l1

    return {
        'mkt_valid': mkt_valid,
        'mkt_above': mkt_above,
        'l1': (l1_above, l1_valid),
        'l2': (l2_above, l2_valid),
        'l2_parent': l2_parent,
    }


def compute_self_breadth(
    close_series: dict[str, Any],
    industry_map: dict[str, dict[str, str]],
    periods: tuple[int, ...] = DEFAULT_PERIODS,
    now_bjt: datetime | None = None,
) -> dict[str, Any]:
    dates: list[str] = list(close_series['dates'])
    stocks: dict[str, list[float | None]] = close_series['stocks']
    n_dates = len(dates)
    now_bjt = now_bjt or datetime.now(BJT)
    fresh = _freshness(dates, now_bjt)

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
            'industries_l2': _rows_from(l2_above, l2_valid, dates, parent=acc['l2_parent']),
        }

    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).astimezone(BJT).isoformat(),
        'source': 'self',
        'metric': 'maN_above_ratio',
        'dates': dates,
        # 新鲜度标记 (C3): 供前端"截至X日"展示与 C1 哨兵消费; 陈旧不阻断出图.
        'as_of': fresh['as_of'],
        'expected_date': fresh['expected_date'],
        'stale': fresh['stale'],
        'periods': out_periods,
    }


def run(
    data_root: Path,
    periods: tuple[int, ...] = DEFAULT_PERIODS,
    now_bjt: datetime | None = None,
) -> Path:
    import json

    stocks_dir = Path(data_root) / 'stocks'
    close_series = json.loads((stocks_dir / 'close_series.json').read_text(encoding='utf-8'))
    map_path = stocks_dir / 'stock_industry_map.json'
    industry_map = json.loads(map_path.read_text(encoding='utf-8'))['map'] if map_path.exists() else {}

    snapshot = compute_self_breadth(close_series, industry_map, periods, now_bjt=now_bjt)
    if snapshot['stale']:
        # 结构化前缀 (C1 哨兵消费契约, 勿改名)
        log.warning('temperature_stale: as_of=%s expected=%s',
                    snapshot['as_of'], snapshot['expected_date'])
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
