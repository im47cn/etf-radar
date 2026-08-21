"""A 股主要指数收盘价时序管线: 按 market_temperature.json 的 dates 对齐 → index_series.json.

输出 schema 1.0:
- dates: 与 market_temperature.json 完全一致 (同序同长), 前端按下标配对免 join.
- indices: [{code, name, series}], series 与 dates 等长, 缺失日 null.

口径:
- provider chain (CLAUDE.md 硬约束): 单指数按 providers 顺序逐级 fetch, 首个成功即采纳,
  全部失败才该列全 null (参照 pipeline.py ETF chain, 简化版无"旧 bar"概念).
- 单指数全源失败不阻断其他指数 (温度链与指数链解耦).
- 指数原始序列按温度图 dates 重对齐 (dict 映射, 缺失填 null, 多余忽略).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from ..output.writer import atomic_write_json
from ..providers.index_provider import EmIndexProvider, IndexProvider, TencentIndexProvider

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


class IndexCloseProvider(Protocol):
    """指数收盘价数据源契约 (消费者依赖抽象, 便于测试注入伪实现)."""

    name: str

    def fetch_close(self, code: str) -> list[tuple[date, float]]:
        """返回 [(date, close), ...] 升序收盘价序列."""
        ...


def _align(dates: list[str], raw: list[tuple[date, float]]) -> list[float | None]:
    """把 (date, close) 原始序列对齐到目标 dates (YYYY-MM-DD 字符串). 缺失位填 None."""
    mapping = {d.isoformat(): v for d, v in raw}
    return [mapping.get(dt) for dt in dates]


def _fetch_with_chain(code: str, providers: list[IndexCloseProvider]) -> list[tuple[date, float]] | None:
    """单指数按 providers 顺序逐级 fetch, 首个成功即返回; 全失败返回 None."""
    for provider in providers:
        try:
            return provider.fetch_close(code)
        except Exception as e:  # noqa: BLE001  chain 兜底, 单源失败试下一源
            log.warning('index %s fetch failed [%s]: %s', code, provider.name, e)
    return None


def build_index_series(
    dates: list[str],
    providers: list[IndexCloseProvider],
    indices: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """按 dates 对齐、按 provider chain 抓取各指数收盘价, 组装 schema 1.0 dict."""
    specs = indices if indices is not None else INDICES
    out_indices: list[dict[str, Any]] = []
    for code, name in specs:
        raw = _fetch_with_chain(code, providers)
        if raw is None:
            log.warning('index %s (%s) 全源失败 — series 全 null', code, name)
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


def run(
    data_root: Path,
    providers: list[IndexCloseProvider] | None = None,
) -> Path:
    """读 market_temperature.json 的 dates → chain 抓指数 → 写 latest/index_series.json.

    温度文件缺失 (首次运行/上游失败) 时写空 index_series.json, 不抛错拖累 cron.
    """
    if providers is None:
        providers = [IndexProvider(), EmIndexProvider(), TencentIndexProvider()]
    temp_path = Path(data_root) / 'latest' / 'market_temperature.json'
    out = Path(data_root) / 'latest' / 'index_series.json'
    if not temp_path.exists():
        log.warning('market_temperature.json 不存在, 写空 index_series.json')
        snapshot = build_index_series([], providers)
        atomic_write_json(out, snapshot)
        return out
    temp = json.loads(temp_path.read_text(encoding='utf-8'))
    dates = list(temp['dates'])
    snapshot = build_index_series(dates, providers)
    atomic_write_json(out, snapshot)
    log.info('index_series written: %d dates, %d indices', len(dates), len(snapshot['indices']))
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
