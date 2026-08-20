"""SEPA 交易信号管线: 全市场 ohlcv + 指数环境 -> data/latest/trading.json.

数据流 (spec 2026-08-20 §2.3):
- 读 data/stocks/ohlcv/{code}.json (M0 产物, qfq, 400 交易日)
- 指数环境: 三指数 + RS 基准中证全指(000985) 走 provider chain (IndexProvider -> EmIndexProvider)
- 名称/ST: ak.stock_zh_a_spot (新浪); 失败降级 name=code、ST 过滤失效并标记 source_status
- 波动: data/stocks/holdings_indicators.json 的 vol_forecast_ann (可得则进综合分, 仅持仓股)
- 宽度佐证: data/latest/market_temperature.json (缺失降级 null)
组件级降级 source_status; 核心失败 (可用指数<2) raise ProviderError (CI 可见)。

运行: uv run python -m src.trading.pipeline --data-root ../data
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import numpy as np
from numpy.typing import NDArray

from ..output.writer import atomic_write_json
from .environment import (
    INDEX_CODES,
    RS_BENCHMARK,
    apply_defense_gating,
    compute_environment,
    read_breadth,
)
from .screen import StockBars, compute_rs_percentiles, r60, screen_universe

log = logging.getLogger(__name__)
BJT = ZoneInfo('Asia/Shanghai')  # 新鲜度判定以北京时间为准 (EOD cron 时区, 口径同 metals)

SCHEMA_VERSION = '1.0'
INDEX_LOOKBACK = 400  # 指数序列取尾 400 根 (52 周 + MA200 斜率 + 余量)
STALE_DAYS = 45  # 指数末条日期距今超过该自然日数视为坏数据 (口径同 M5 回测)
Array = NDArray[np.float64]


class IndexCloseProvider(Protocol):
    """指数收盘 provider 协议 (IndexProvider / EmIndexProvider 及测试桩)。"""

    name: str

    def fetch_close(self, code: str) -> list[tuple[date, float]]: ...


def load_universe(ohlcv_dir: Path) -> dict[str, StockBars]:
    """读 ohlcv/{code}.json (§2.2 格式, 字段 d/o/h/l/c/v/amt); 损坏文件跳过并告警。"""
    universe: dict[str, StockBars] = {}
    if not ohlcv_dir.is_dir():
        return universe
    for fp in sorted(ohlcv_dir.glob('*.json')):
        try:
            doc = json.loads(fp.read_text(encoding='utf-8'))
            bars = doc['bars']
            universe[str(doc['code'])] = StockBars(
                code=str(doc['code']),
                open_=np.array([float(b['o']) for b in bars], dtype=np.float64),
                high=np.array([float(b['h']) for b in bars], dtype=np.float64),
                low=np.array([float(b['l']) for b in bars], dtype=np.float64),
                close=np.array([float(b['c']) for b in bars], dtype=np.float64),
                volume=np.array([float(b['v']) for b in bars], dtype=np.float64),
                amount=np.array([float(b.get('amt', 0.0)) for b in bars], dtype=np.float64),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
            log.warning('trading ohlcv skip %s: %s', fp.name, e)
    return universe


def fetch_index_close(code: str, providers: list[IndexCloseProvider]) -> Array | None:
    """指数收盘走 provider chain 逐级兜底 (CLAUDE.md 硬约束); 全失败返回 None。

    新鲜度护栏: 末条日期距今 >45 自然日视为坏数据 (如新浪 sh000985 只维护到
    2016, 会"成功返回陈旧数据"而非报错), 同样落入 chain 兜底 — 口径与 M5
    回测 (scripts/research/sepa_backtest.py) 一致。
    """
    stale_before = datetime.now(BJT).date() - timedelta(days=STALE_DAYS)
    for p in providers:
        try:
            rows = p.fetch_close(code)
            if rows and rows[-1][0] >= stale_before:
                return np.array([c for _, c in rows[-INDEX_LOOKBACK:]], dtype=np.float64)
            last = rows[-1][0] if rows else 'empty'
            log.warning('trading index %s via %s stale (last=%s), fall to next', code, p.name, last)
        except Exception as e:  # noqa: BLE001  chain 兜底, 单源失败试下一源
            log.warning('trading index %s via %s failed: %s', code, p.name, e)
    return None


def fetch_spot_names() -> dict[str, str]:
    """新浪全市场 spot -> {code: name} (ST/退市标记与展示名来源)。"""
    import akshare as ak  # type: ignore[import-untyped]

    df = ak.stock_zh_a_spot()
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        code = str(row['代码']).replace('sh', '').replace('sz', '').replace('bj', '')
        out[code] = str(row['名称'])
    return out


def load_vol_map(data_root: Path) -> dict[str, float | None]:
    """holdings_indicators.json 的 vol_forecast_ann (仅持仓股可得, 其余不进 map)。"""
    try:
        doc = json.loads((Path(data_root) / 'stocks' / 'holdings_indicators.json').read_text(encoding='utf-8'))
        return {str(c): s.get('vol_forecast_ann') for c, s in doc['stocks'].items()}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _default_spot() -> tuple[dict[str, str], bool]:
    """默认 spot 拉取; 失败降级空 dict (name=code, ST 过滤失效, source_status 标记)。"""
    try:
        names = fetch_spot_names()
        return names, bool(names)
    except Exception as e:  # noqa: BLE001  组件级降级
        log.warning('trading spot names degraded: %s', e)
        return {}, False


def run(
    data_root: Path,
    index_providers: list[IndexCloseProvider] | None = None,
    spot_names: dict[str, str] | None = None,
) -> Path:
    """拉数据 -> 漏斗 -> defense gating -> 写 data_root/latest/trading.json。"""
    if index_providers is None:
        from ..providers.index_provider import EmIndexProvider, IndexProvider

        index_providers = [IndexProvider(), EmIndexProvider()]
    data_root = Path(data_root)

    # 1) 指数环境 (核心: 三指数可用 <2 只 -> ProviderError)
    closes = {code: fetch_index_close(code, index_providers) for code in [*INDEX_CODES, RS_BENCHMARK]}
    alive = {c: arr for c, arr in closes.items() if arr is not None}
    environment = compute_environment({c: alive[c] for c in INDEX_CODES if c in alive})

    # 2) RS 基准 (中证全指 60 日收益); 全 chain 失败 -> RS 整体降级
    bench = alive.get(RS_BENCHMARK)
    bench_r60 = r60(bench) if bench is not None else None

    # 3) 全市场 universe + 名称 + RS 分位 (横截面含未过滤股票, 基准更广)
    universe = load_universe(data_root / 'stocks' / 'ohlcv')
    names, spot_ok = (spot_names, True) if spot_names is not None else _default_spot()
    r60_map: dict[str, float] = {}
    for code, bars in universe.items():
        r = r60(bars.close)
        if r is not None:
            r60_map[code] = r
    rs_pct = compute_rs_percentiles(r60_map, bench_r60)

    # 4) 漏斗 + 综合分 + defense gating
    vol_map = load_vol_map(data_root)
    candidates, stats = screen_universe(universe, names, rs_pct, vol_map)
    candidates = apply_defense_gating(candidates, environment['regime'])

    breadth = read_breadth(data_root)
    n_env = sum(1 for c in INDEX_CODES if c in alive)
    snapshot: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.now(UTC).isoformat(),
        'environment': {
            **environment,
            'breadth': breadth,
            'source_status': {
                'indices': 'ok' if n_env == len(INDEX_CODES) else 'partial',
                'rs_benchmark': 'ok' if bench_r60 is not None else 'missing',
                'spot': 'ok' if spot_ok else 'missing',
                'breadth': 'ok' if breadth is not None else 'missing',
                'universe': 'ok' if universe else 'empty',
                'vol': 'ok' if vol_map else 'missing',
            },
        },
        'candidates': candidates,
        'universe_stats': stats,
    }
    out = data_root / 'latest' / 'trading.json'
    atomic_write_json(out, snapshot)
    log.info(
        'trading written: regime=%s, candidates=%d, stats=%s, rs_benchmark=%s',
        environment['regime'], len(candidates), stats, 'ok' if bench_r60 is not None else 'missing',
    )
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    parser = argparse.ArgumentParser(description='SEPA 交易信号管线')
    parser.add_argument('--data-root', type=Path, default=Path('../data'))
    args = parser.parse_args()
    run(args.data_root)


if __name__ == '__main__':
    main()
