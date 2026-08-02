"""A 股主要指数收盘价时序管线: 按 market_temperature.json 的 dates 对齐 → index_series.json.

输出 schema 1.0:
- dates: 与 market_temperature.json 完全一致 (同序同长), 前端按下标配对免 join.
- indices: [{code, name, series}], series 与 dates 等长, 缺失日 null.

口径:
- 单指数抓取失败: series 全 null + warning, 不阻断其他指数 (温度链与指数链解耦).
- 指数原始序列按温度图 dates 重对齐 (dict 映射, 缺失填 null, 多余忽略).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..output.writer import atomic_write_json
from ..providers.index_provider import IndexCloseProvider, IndexProvider

log = logging.getLogger(__name__)
BJT = ZoneInfo('Asia/Shanghai')
SCHEMA_VERSION = '1.0'

# (code, name) — 6 只 A 股主要指数, 覆盖大盘/深市/成长/蓝筹/科创
INDICES: list[tuple[str, str]] = [
    ('000001', '上证指数'),
    ('399001', '深证成指'),
    ('399006', '创业板指'),
    ('000300', '沪深300'),
    ('000688', '科创50'),
    ('000698', '科创100'),
]


def _align(dates: list[str], raw: list[tuple[date, float]]) -> list[float | None]:
    """把 (date, close) 原始序列对齐到目标 dates (YYYY-MM-DD 字符串). 缺失位填 None."""
    mapping = {d.isoformat(): v for d, v in raw}
    return [mapping.get(dt) for dt in dates]


def build_index_series(
    dates: list[str],
    provider: IndexCloseProvider,
    indices: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """按 dates 对齐抓取各指数收盘价, 组装 schema 1.0 dict."""
    specs = indices if indices is not None else INDICES
    out_indices: list[dict[str, Any]] = []
    for code, name in specs:
        try:
            raw = provider.fetch_close(code)
        except Exception as e:  # noqa: BLE001  外部数据源兜底, 单指数失败不影响其他
            log.warning('index %s (%s) fetch failed: %s — series 全 null', code, name, e)
            series: list[float | None] = [None] * len(dates)
        else:
            series = _align(dates, raw)
            non_null = sum(1 for v in series if v is not None)
            log.info('index %s (%s) aligned: %d/%d non-null', code, name, non_null, len(dates))
        out_indices.append({'code': code, 'name': name, 'series': series})
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.now(UTC).astimezone(BJT).isoformat(),
        'dates': dates,
        'indices': out_indices,
    }


def run(data_root: Path, provider: IndexCloseProvider | None = None) -> Path:
    """读 market_temperature.json 的 dates → 抓指数 → 写 latest/index_series.json."""
    if provider is None:
        provider = IndexProvider()
    temp_path = Path(data_root) / 'latest' / 'market_temperature.json'
    temp = json.loads(temp_path.read_text(encoding='utf-8'))
    dates = list(temp['dates'])
    snapshot = build_index_series(dates, provider)
    out = Path(data_root) / 'latest' / 'index_series.json'
    atomic_write_json(out, snapshot)
    log.info(
        'index_series written: %d dates, %d indices', len(dates), len(snapshot['indices'])
    )
    return out


def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    parser = argparse.ArgumentParser(description='A 股主要指数收盘价时序管线')
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    run(args.data_root)


if __name__ == '__main__':
    main()
