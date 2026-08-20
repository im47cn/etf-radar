"""全市场个股 OHLCV(qfq) 归档管线 — SEPA 交易闭环 Lane M0 (spec §2.2).

入口:
  python -m src.stocks_ohlcv_pipeline                每日增量 (CI; 默认 max_workers=4)
  python -m src.stocks_ohlcv_pipeline --backfill     本地全量 (默认 max_workers=1 防新浪限速)

写入:
  data/stocks/ohlcv/{code}.json
  {"schema_version":"1.0","code":"600519","bars":[{"d","o","h","l","c","v","amt"},...]}
  qfq 前复权, 日期升序, 滚动 400 交易日。

设计说明:
- 不复用 StockHistoryProvider.fetch_history: 其 StockOhlcBar 无成交额(amt)字段,
  而 spec §2.2 要求 amt (M1 流动性过滤"20 日日均成交额"依赖); 此处复用其
  to_sina_symbol 前缀映射与指数退避模式, 直接解析含 amount 列的 DataFrame。
- merge 防回退护栏 (类比 stocks_history_pipeline._guard_no_regress):
  拉取结果只到 T-1 而现有文件已含 T (增量已写入) 时, T bar 保留 — 旧 bar
  不得覆盖新 bar; 同日冲突以新拉取值刷新。
- 新浪接口固定返回全历史; qfq 前复权因子随除权变动会改写整窗, 故增量也
  整窗拉取后截尾 days, 不按日期区间增量拉。
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import akshare as ak  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from .output.writer import atomic_write_json
from .providers.stock_history_provider import to_sina_symbol
from .stocks_history_pipeline import BackfillReport, _fetch_universe

log = logging.getLogger(__name__)

# 滚动窗口: 52 周高/低 + 200MA + VCP 60 窗 + 余量 (spec §2.2)
KEEP_DAYS = 400


class OhlcvFetchError(Exception):
    """OHLCV 抓取失败（含重试耗尽与空返回）"""


@dataclass(slots=True)
class OhlcvBar:
    """单日 bar, 字段名与 spec §2.2 JSON 键一致。"""

    d: str  # 交易日 ISO 日期
    o: float
    h: float
    l: float
    c: float
    v: int
    amt: float  # 成交额(元)


def fetch_ohlcv(
    code: str,
    days: int = KEEP_DAYS,
    max_retries: int = 3,
    base_backoff: float = 0.5,
) -> list[OhlcvBar]:
    """拉单只个股 qfq 日线 (含成交额), 指数退避重试, 截尾最近 days 个交易日。"""
    symbol = to_sina_symbol(code)
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            df: pd.DataFrame = ak.stock_zh_a_daily(symbol=symbol, adjust='qfq')
            if df is None or df.empty:
                raise OhlcvFetchError(f'{code}: empty dataframe')
            return _df_to_bars(code, df, days)
        except OhlcvFetchError:
            raise
        except Exception as e:  # noqa: BLE001  外部数据源兜底
            last_err = e
            if attempt < max_retries:
                backoff = base_backoff * (2 ** attempt)
                log.warning(f'{code} retry {attempt + 1} after {backoff}s: {e}')
                time.sleep(backoff)
    raise OhlcvFetchError(f'{code} fetch failed: {last_err}')


def _df_to_bars(code: str, df: pd.DataFrame, days: int) -> list[OhlcvBar]:
    """DataFrame → OhlcvBar 列表; 跳过缺值/非正值行 (qfq 老股早期价格~0 护栏)。"""
    df = df.tail(days)
    bars: list[OhlcvBar] = []
    skipped = 0
    for _, row in df.iterrows():
        try:
            o, h, l, c = (float(row[k]) for k in ('open', 'high', 'low', 'close'))
            v = int(row['volume'])
            amt = float(row['amount'])
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if any(math.isnan(x) for x in (o, h, l, c, amt)) or c <= 0 or v < 0:
            skipped += 1
            continue
        dt = row['date']
        d = dt.date() if hasattr(dt, 'date') else str(dt)
        bars.append(OhlcvBar(d=d.isoformat() if hasattr(d, 'isoformat') else d,
                             o=o, h=h, l=l, c=c, v=v, amt=amt))
    if skipped:
        log.warning(f'{code}: skip {skipped} bad rows (qfq 老股/缺值护栏)')
    return bars


def merge_bars(
    existing: list[OhlcvBar],
    new: list[OhlcvBar],
    keep: int = KEEP_DAYS,
) -> list[OhlcvBar]:
    """防回退合并: 同日新 bar 覆盖旧 bar; 现有文件中更新的尾部日期保留。

    场景: 盘后增量已写入 T bar, 之后跑的拉取结果只到 T-1 (历史接口当日
    未 roll 出) → T 保留不回退。输出按日期升序, 只留末 keep 条。
    """
    merged = {b.d: b for b in existing}
    merged.update({b.d: b for b in new})  # 同日 new 优先
    return sorted(merged.values(), key=lambda b: b.d)[-keep:]


def _load_existing(path: Path) -> list[OhlcvBar]:
    """读现有 {code}.json 的 bars; 损坏文件当作空 (下轮全量覆盖, 不阻断他股)。"""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        log.warning(f'{path.name}: unreadable, treat as empty')
        return []
    bars: list[OhlcvBar] = []
    for raw in data.get('bars', []):
        try:
            bars.append(OhlcvBar(
                d=str(raw['d']), o=float(raw['o']), h=float(raw['h']),
                l=float(raw['l']), c=float(raw['c']), v=int(raw['v']),
                amt=float(raw['amt']),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return bars


def _write_bars(out_dir: Path, code: str, bars: list[OhlcvBar]) -> None:
    atomic_write_json(out_dir / f'{code}.json', {
        'schema_version': '1.0',
        'code': code,
        'bars': [asdict(b) for b in bars],
    })


def run_ohlcv_pipeline(
    out_dir: Path,
    days: int = KEEP_DAYS,
    max_workers: int = 4,
    codes: list[str] | None = None,
) -> BackfillReport:
    """全市场 (或指定 codes) 拉取 → merge 防回退 → 原子写; 单只失败隔离。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    universe = codes if codes is not None else _fetch_universe()
    log.info(f'ohlcv universe={len(universe)} days={days} max_workers={max_workers}')
    report = BackfillReport()

    def process_one(code: str) -> None:
        try:
            new_bars = fetch_ohlcv(code, days=days)
        except OhlcvFetchError as e:
            report.failed.append(code)
            log.warning(f'{code} failed: {e}')
            return
        except Exception as e:  # noqa: BLE001  兜底:未知异常不阻断其他个股
            report.failed.append(code)
            log.warning(f'{code} unexpected: {e}')
            return
        if not new_bars:
            report.failed.append(code)
            log.warning(f'{code}: no valid bars')
            return
        path = out_dir / f'{code}.json'
        merged = merge_bars(_load_existing(path), new_bars, keep=days)
        _write_bars(out_dir, code, merged)
        report.success.append(code)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(process_one, c) for c in universe]
        for fut in as_completed(futures):
            fut.result()

    log.info(f'ohlcv done: success={report.success_count} failed={report.failed_count}')
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--days', type=int, default=KEEP_DAYS)
    parser.add_argument('--max-workers', type=int, default=None,
                        help='默认: --backfill 为 1 (防新浪限速), 增量为 4')
    parser.add_argument('--backfill', action='store_true',
                        help='本地全量模式 (与增量同逻辑, 仅默认并发不同)')
    parser.add_argument('--codes', nargs='*', default=None,
                        help='只处理指定 code (样例数据生成/调试)')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    if args.max_workers is not None:
        max_workers = args.max_workers
    else:
        max_workers = 1 if args.backfill else 4
    report = run_ohlcv_pipeline(
        out_dir=args.data_root / 'stocks' / 'ohlcv',
        days=args.days,
        max_workers=max_workers,
        codes=args.codes,
    )
    # 全员失败 = 数据源不可用, 响亮失败防静默停更 (EOD 归档停更 5 周先例);
    # 部分失败 (新股/退市股) 属正常噪音, 不拦。
    if report.failed_count and not report.success_count:
        log.error(f'all {report.failed_count} fetches failed — data source down?')
        sys.exit(1)


if __name__ == '__main__':  # pragma: no cover
    main()
