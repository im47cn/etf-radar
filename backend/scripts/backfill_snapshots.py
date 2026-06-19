"""Snapshots 回填脚本

用法:
    python -m scripts.backfill_snapshots --start 2026-01-02 --end 2026-06-13

设计:
    1. 一次拉所有 symbol 的足够长历史 (lookback = days_in_window + 200)
    2. 遍历 [start, end] 工作日 D, 内存切片 cache 到 <= D
    3. 调用 compute_outputs(asof_bjt=D 当晚 16:00 BJT) 计算
    4. 写 data/snapshots/<D>/{themes,signals,etfs,meta}.json
    5. 末尾生成 latest/snapshots-index.json

关键事实:
    - 所有 scoring 函数已 as-of-friendly, 零改动
    - lookback 包括 buffer 是为了覆盖 r_120d 窗口 + r_ytd 跨年起点
    - meta.json 标记 backfilled=true 区分真实归档
"""
from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import date, datetime, time as dtime
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
from tqdm import tqdm  # type: ignore[import-not-found]

from src.config_loader import load_algo_config, load_themes
from src.etl.calendar import BJT, is_cn_trading_day, is_us_trading_day
from src.output.snapshots_index import write_snapshots_index
from src.output.writer import atomic_write_json
from src.pipeline import PipelineMode, compute_outputs
from src.providers.akshare_em_provider import AkshareEmProvider
from src.providers.base import EmptyDataError, EtfDataProvider, ProviderError
from src.providers.yfinance_provider import YfinanceProvider

log = logging.getLogger(__name__)


def _collect_history(
    symbols: list[str], provider: EtfDataProvider, lookback_days: int,
    label: str, jitter_range: tuple[float, float] = (0.0, 0.0),
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """一次性拉所有 symbol 的历史, jitter 仅在 CN provider 用 (yfinance 不需要)。"""
    cache: dict[str, pd.DataFrame] = {}
    failed: list[str] = []
    for sym in tqdm(symbols, desc=f'fetch {label}', unit='sym'):
        try:
            cache[sym] = provider.fetch_ohlc(sym, lookback_days=lookback_days)
        except (ProviderError, EmptyDataError) as e:
            log.warning(f'{label} fetch failed {sym}: {e}')
            failed.append(sym)
        if jitter_range[1] > 0:
            time.sleep(random.uniform(*jitter_range))
    return cache, failed


def _slice_to_date(cache: dict[str, pd.DataFrame], D: date) -> dict[str, pd.DataFrame]:
    """内存切片: 每个 df 截到 date <= D"""
    out: dict[str, pd.DataFrame] = {}
    for sym, df in cache.items():
        sliced = df[df['date'].dt.date <= D]
        if not sliced.empty:
            out[sym] = sliced
    return out


def _iter_trading_days(start: date, end: date) -> list[date]:
    """生成 [start, end] 范围内的 BJT 工作日 (CN 或 US 任一开市)。"""
    out: list[date] = []
    d = start
    while d <= end:
        if is_cn_trading_day(d) or is_us_trading_day(d):
            out.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    return out


def backfill(
    start: date, end: date, data_root: Path, config_dir: Path,
    lookback_days: int | None = None,
    skip_existing: bool = True, force: bool = False, write_index: bool = True,
) -> None:
    if force and skip_existing:
        raise ValueError('--force and --skip-existing are mutually exclusive')

    themes = load_themes(config_dir / 'themes.yml')
    algo = load_algo_config(config_dir / 'algo.yml')

    today = datetime.now(tz=BJT).date()
    if lookback_days is None:
        # (today - start) days + 200 buffer (覆盖 r_120d + r_ytd 跨年起点)
        lookback_days = (today - start).days + 200
    log.info(f'lookback_days={lookback_days}')

    us_symbols = sorted({sym for t in themes for sym in t.us_etfs})
    cn_codes = sorted({cn.code for t in themes for cn in t.cn_etfs})

    log.info(f'fetching {len(us_symbols)} US symbols')
    us_cache, us_failed_init = _collect_history(
        us_symbols, YfinanceProvider(), lookback_days, 'US',
    )
    log.info(f'fetching {len(cn_codes)} CN codes (with jitter)')
    cn_cache, cn_failed_init = _collect_history(
        cn_codes, AkshareEmProvider(), lookback_days, 'CN', jitter_range=(0.3, 1.0),
    )
    log.info(f'US fetched={len(us_cache)}, failed={len(us_failed_init)}')
    log.info(f'CN fetched={len(cn_cache)}, failed={len(cn_failed_init)}')

    trading_days = _iter_trading_days(start, end)
    log.info(f'backfilling {len(trading_days)} trading days [{start} .. {end}]')

    written = 0
    skipped = 0
    for D in tqdm(trading_days, desc='backfill', unit='day'):
        snap_dir = data_root / 'snapshots' / D.strftime('%Y-%m-%d')
        if skip_existing and (snap_dir / 'themes.json').exists():
            skipped += 1
            continue

        us_sliced = _slice_to_date(us_cache, D)
        cn_sliced = _slice_to_date(cn_cache, D)
        us_failed_D = [s for s in us_symbols if s not in us_sliced]
        cn_failed_D = [c for c in cn_codes if c not in cn_sliced]

        asof = datetime.combine(D, dtime(16, 0), tzinfo=BJT)
        themes_json, etfs_json, signals_json, meta_json = compute_outputs(
            themes, us_sliced, cn_sliced, us_failed_D, cn_failed_D, algo,
            asof_bjt=asof, mode=PipelineMode.FULL, backfilled=True,
        )

        atomic_write_json(snap_dir / 'themes.json', themes_json)
        atomic_write_json(snap_dir / 'etfs.json', etfs_json)
        atomic_write_json(snap_dir / 'signals.json', signals_json)
        atomic_write_json(snap_dir / 'meta.json', meta_json)
        written += 1

    log.info(f'backfill done: written={written}, skipped={skipped}')

    if write_index:
        path = write_snapshots_index(data_root)
        log.info(f'snapshots index: {path}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Backfill snapshots from historical OHLC')
    parser.add_argument('--start', type=date.fromisoformat, required=True,
                        help='起始日期 YYYY-MM-DD (含)')
    parser.add_argument('--end', type=date.fromisoformat, required=True,
                        help='结束日期 YYYY-MM-DD (含)')
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--config-dir', type=Path, default=Path('config'))
    parser.add_argument('--lookback', type=int, default=None,
                        help='历史拉取窗口天数 (默认自动算)')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                        help='跳过已存在的 snapshot 目录 (默认 true)')
    parser.add_argument('--force', action='store_true',
                        help='强制覆盖已存在的 snapshot (覆盖 --skip-existing)')
    parser.add_argument('--no-index', action='store_true',
                        help='跳过 snapshots-index.json 生成')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    skip_existing = args.skip_existing and not args.force
    backfill(
        start=args.start, end=args.end,
        data_root=args.data_root, config_dir=args.config_dir,
        lookback_days=args.lookback,
        skip_existing=skip_existing, force=args.force,
        write_index=not args.no_index,
    )


if __name__ == '__main__':
    main()
