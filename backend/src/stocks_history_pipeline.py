"""一次性历史 K 线 backfill 管道。

入口:
  python -m src.stocks_history_pipeline [--days 150] [--max-workers 4]

写入:
  data/stocks/close_series.json        全市场收盘价矩阵
  data/stocks/volume_series.json       全市场成交量矩阵
  data/stocks/ohlc/{code}.json         holdings 涉及个股 60 日 OHLC
  data/stocks/index.json               索引（含 ohlc_codes / last_trade_date）

注意：
- close_series / volume_series 包含全市场（~5000 只）用于 daily pipeline 算强度
- ohlc/*.json 仅写 holdings 涉及个股，避免 5000 文件
"""
from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak  # type: ignore[import-untyped]

from .models import StockOhlc, StockOhlcBar
from .providers.stock_history_provider import (
    StockHistoryFetchError,
    StockHistoryProvider,
)

log = logging.getLogger(__name__)


@dataclass
class BackfillReport:
    success: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def success_count(self) -> int: return len(self.success)
    @property
    def failed_count(self) -> int: return len(self.failed)


_SINA_PREFIX_RE = r'^(sh|sz|bj)'


def _fetch_universe() -> list[str]:
    """从 akshare 新浪 spot 拉全市场股票 code 列表，剥前缀返回 6 位。

    新浪 spot 的「代码」列已带 sh/sz/bj 前缀（如 'sh600519'），下游统一用 6 位
    作为 universe/series 的 key。
    """
    df = ak.stock_zh_a_spot()
    codes: list[str] = (
        df['代码'].astype(str).str.replace(_SINA_PREFIX_RE, '', regex=True).tolist()
    )
    return codes


def _read_holdings_codes(holdings_dir: Path) -> set[str]:
    codes: set[str] = set()
    for fp in holdings_dir.glob('*.json'):
        if fp.name == 'index.json':
            continue
        data = json.loads(fp.read_text(encoding='utf-8'))
        for h in data.get('top_holdings', []):
            codes.add(h['code'])
    return codes


def _guard_no_regress(
    existing_path: Path,
    new_dates: list,
    new_matrix: dict,
    days: int,
) -> tuple[list[str], dict]:
    """写入护栏: 防 backfill 全量覆盖回退掉 daily 已 append 的最新 bar.

    触发场景: 某交易日 T 盘后 daily 已写入 T 格, 之后手动跑 backfill, 而历史 K 线
    接口当日尚未 roll 出 T bar (只到 T-1). 若直接覆盖, T 格会回退消失 (次日 daily 才补回).
    护栏: 若现有 series 末位日期晚于 backfill 结果末位, 把现有更新的尾部列拼回后再截窗.
    与 daily 的 _append_series 互补: daily 防自身重复追加, 本护栏防 backfill 覆盖 daily.
    """
    new_date_strs: list[str] = [d.isoformat() for d in new_dates]
    if not existing_path.exists() or not new_date_strs:
        return new_date_strs, new_matrix
    try:
        existing = json.loads(existing_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return new_date_strs, new_matrix
    ex_dates: list[str] = existing.get('dates', [])
    ex_stocks: dict[str, list] = existing.get('stocks', {})
    # 现有中晚于 backfill 末位的日期 = backfill 缺失、需保留的更新格
    tail = [d for d in ex_dates if d > new_date_strs[-1]]
    if not tail:
        return new_date_strs, new_matrix  # 无回退, 正常覆盖
    ex_pos = {d: i for i, d in enumerate(ex_dates)}
    codes = set(new_matrix) | set(ex_stocks)
    merged: dict[str, list] = {}
    for code in codes:
        base = list(new_matrix.get(code, [None] * len(new_date_strs)))
        if len(base) < len(new_date_strs):
            base += [None] * (len(new_date_strs) - len(base))
        ex_row = ex_stocks.get(code, [])
        tail_vals = [ex_row[ex_pos[d]] if ex_pos[d] < len(ex_row) else None for d in tail]
        merged[code] = (base + tail_vals)[-days:]
    log.warning(
        f'no-regress guard: backfill 末位 {new_date_strs[-1]} 旧于现有 {tail[-1]}, '
        f'保留 {len(tail)} 个最新格'
    )
    return (new_date_strs + tail)[-days:], merged


def run_history_backfill(
    holdings_dir: Path,
    out_dir: Path,
    days: int = 75,
    max_workers: int = 4,
) -> BackfillReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    ohlc_dir = out_dir / 'ohlc'
    ohlc_dir.mkdir(exist_ok=True)

    holdings_codes = _read_holdings_codes(holdings_dir)
    universe = _fetch_universe()
    log.info(f'universe={len(universe)} holdings_codes={len(holdings_codes)}')

    provider = StockHistoryProvider()
    report = BackfillReport()
    results: dict[str, list[StockOhlcBar]] = {}

    def fetch_one(code: str) -> tuple[str, list[StockOhlcBar] | None, str | None]:
        try:
            bars = provider.fetch_history(code, days=days)
            return code, bars, None
        except StockHistoryFetchError as e:
            return code, None, str(e)
        except Exception as e:
            return code, None, f'unexpected: {e}'

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, c): c for c in universe}
        for fut in as_completed(futures):
            code, bars, err = fut.result()
            if bars is None:
                report.failed.append(code)
                log.warning(f'{code} failed: {err}')
                continue
            results[code] = bars
            report.success.append(code)

    # 收集所有出现过的日期（按出现顺序集中）
    all_dates = sorted({b.date for bars in results.values() for b in bars})
    all_dates = all_dates[-days:]
    date_idx = {d: i for i, d in enumerate(all_dates)}

    close_matrix: dict[str, list[float | None]] = {}
    volume_matrix: dict[str, list[int | None]] = {}
    for code, bars in results.items():
        closes: list[float | None] = [None] * len(all_dates)
        volumes: list[int | None] = [None] * len(all_dates)
        for b in bars:
            if b.date in date_idx:
                closes[date_idx[b.date]] = b.c
                volumes[date_idx[b.date]] = b.v
        close_matrix[code] = closes
        volume_matrix[code] = volumes

    # 写入护栏: 防 backfill 覆盖回退掉 daily 已 append 的最新 bar
    close_dates, close_matrix = _guard_no_regress(
        out_dir / 'close_series.json', all_dates, close_matrix, days)
    volume_dates, volume_matrix = _guard_no_regress(
        out_dir / 'volume_series.json', all_dates, volume_matrix, days)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (out_dir / 'close_series.json').write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': now,
        'dates': close_dates,
        'stocks': close_matrix,
    }, ensure_ascii=False))
    (out_dir / 'volume_series.json').write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': now,
        'dates': volume_dates,
        'stocks': volume_matrix,
    }, ensure_ascii=False))

    # 写 holdings 涉及个股的 60 日 OHLC
    ohlc_codes: list[str] = []
    for code in sorted(holdings_codes & set(results.keys())):
        bars = results[code][-60:]
        snap = StockOhlc(
            code=code, name=code,
            generated_at=datetime.fromisoformat(now),
            bars=bars,
        )
        (ohlc_dir / f'{code}.json').write_text(
            snap.model_dump_json(),
            encoding='utf-8',
        )
        ohlc_codes.append(code)

    (out_dir / 'index.json').write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': now,
        'ohlc_codes': ohlc_codes,
        'last_trade_date': close_dates[-1] if close_dates else None,
    }, ensure_ascii=False))

    log.info(f'backfill done: success={report.success_count} failed={report.failed_count}')
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--days', type=int, default=150)  # 150 交易日: 给 MA120 宽度留 ~30 日序列 buffer
    parser.add_argument('--max-workers', type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    run_history_backfill(
        holdings_dir=args.data_root / 'holdings',
        out_dir=args.data_root / 'stocks',
        days=args.days,
        max_workers=args.max_workers,
    )


if __name__ == '__main__':
    main()
