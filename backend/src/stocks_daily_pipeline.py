"""工作日盘后 daily 增量管道。

入口:
  python -m src.stocks_daily_pipeline [--data-root ./data]

步骤:
  1) 读 data/stocks/close_series.json + volume_series.json
  2) 拉今日 ak.stock_zh_a_spot_em → 追加一行 → 截窗 75
  3) 全市场批量算 r_5d / r_20d / r_60d → batch_strength
  4) 遍历 holdings 个股算 RSI / 量比 / leader
  5) 写 close_series / volume_series / holdings_indicators / ohlc/{code} / index
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import akshare as ak  # type: ignore[import-untyped]
import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from .scoring.leader_rule import classify_leader
from .scoring.stock_indicators import compute_rsi, compute_volume_ratio
from .scoring.strength import batch_strength_per_dim

log = logging.getLogger(__name__)

WINDOW_DAYS = 75
K_SIGMOID = 2.0


def _fetch_today_spot() -> pd.DataFrame:
    return ak.stock_zh_a_spot_em()


def _read_holdings_codes(holdings_dir: Path) -> set[str]:
    codes: set[str] = set()
    for fp in holdings_dir.glob('*.json'):
        if fp.name == 'index.json':
            continue
        data = json.loads(fp.read_text(encoding='utf-8'))
        for h in data.get('top_holdings', []):
            codes.add(h['code'])
    return codes


def _read_holdings_names(holdings_dir: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for fp in holdings_dir.glob('*.json'):
        if fp.name == 'index.json':
            continue
        data = json.loads(fp.read_text(encoding='utf-8'))
        for h in data.get('top_holdings', []):
            names[h['code']] = h['name']
    return names


def _append_series(series_data: dict[str, Any], today: date, today_values: dict[str, float | int | None]) -> dict[str, Any]:
    """追加今日一格，截窗保留尾部 WINDOW_DAYS 行。"""
    new_dates = series_data['dates'] + [today.isoformat()]
    new_dates = new_dates[-WINDOW_DAYS:]
    new_stocks: dict[str, list[float | int | None]] = {}
    for code, hist in series_data['stocks'].items():
        appended = hist + [today_values.get(code)]
        new_stocks[code] = appended[-WINDOW_DAYS:]
    # 处理今日新增的股（之前 series 没有）
    for code, val in today_values.items():
        if code not in new_stocks:
            n_existing = len(new_dates) - 1
            padded: list[float | int | None] = []
            padded.extend([None] * n_existing)
            padded.append(val)
            new_stocks[code] = padded[-WINDOW_DAYS:]
    series_data['dates'] = new_dates
    series_data['stocks'] = new_stocks
    return series_data


def _compute_n_day_return(closes: list[float | None], n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    today = closes[-1]
    past = closes[-n - 1]
    if today is None or past is None or past <= 0:
        return None
    return (today - past) / past


def run_daily_pipeline(
    holdings_dir: Path,
    out_dir: Path,
    today: date | None = None,
) -> None:
    today = today or date.today()
    close_path = out_dir / 'close_series.json'
    volume_path = out_dir / 'volume_series.json'
    indicators_path = out_dir / 'holdings_indicators.json'

    close_data = json.loads(close_path.read_text(encoding='utf-8'))
    volume_data = json.loads(volume_path.read_text(encoding='utf-8'))

    # 拉今日 spot；失败则不覆盖现有 indicators
    try:
        spot_df = _fetch_today_spot()
    except Exception as e:
        log.error(f'spot fetch failed: {e}; keeping existing indicators untouched')
        return

    today_close = {str(r['代码']): float(r['最新价']) for _, r in spot_df.iterrows()
                   if pd.notna(r['最新价'])}
    today_volume = {str(r['代码']): int(r['成交量']) for _, r in spot_df.iterrows()
                    if pd.notna(r['成交量'])}

    close_data = _append_series(close_data, today, today_close)  # type: ignore[arg-type]
    volume_data = _append_series(volume_data, today, today_volume)  # type: ignore[arg-type]

    # 计算全市场强度
    universe = list(close_data['stocks'].keys())
    r_60d_raw = [_compute_n_day_return(close_data['stocks'][c], 60) for c in universe]
    r_20d_raw = [_compute_n_day_return(close_data['stocks'][c], 20) for c in universe]

    r_60d_arr = np.array([np.nan if v is None else v for v in r_60d_raw], dtype=float)
    r_20d_arr = np.array([np.nan if v is None else v for v in r_20d_raw], dtype=float)

    s60 = batch_strength_per_dim(r_60d_arr, k=K_SIGMOID, days_in_dim=60)
    s20 = batch_strength_per_dim(r_20d_arr, k=K_SIGMOID, days_in_dim=20)
    s60_map = dict(zip(universe, s60))
    s20_map = dict(zip(universe, s20))

    # 遍历 holdings 算 indicators
    holdings_codes = _read_holdings_codes(holdings_dir)
    holdings_names = _read_holdings_names(holdings_dir)
    indicators: dict[str, dict[str, Any]] = {}
    for code in holdings_codes:
        if code not in close_data['stocks']:
            continue
        closes = close_data['stocks'][code]
        volumes = volume_data['stocks'].get(code, [])
        s60_v = s60_map.get(code)
        s20_v = s20_map.get(code)
        s60_int: int | None = None if (s60_v is None or np.isnan(s60_v)) else int(s60_v)
        s20_int: int | None = None if (s20_v is None or np.isnan(s20_v)) else int(s20_v)
        rsi = compute_rsi(closes)
        vr = compute_volume_ratio(volumes)
        leader = classify_leader(s60_int, rsi)
        indicators[code] = {
            'name': holdings_names.get(code, code),
            'strength_60d': s60_int,
            'strength_20d': s20_int,
            'rsi_14': rsi,
            'vol_ratio': vr,
            'leader': leader,
        }

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    indicators_path.write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': now,
        'stocks': indicators,
    }, ensure_ascii=False))
    close_path.write_text(json.dumps(close_data, ensure_ascii=False))
    volume_path.write_text(json.dumps(volume_data, ensure_ascii=False))

    # 更新 holdings 个股的 60 日 OHLC（基于 close_series + volume_series 末 60 行重建）
    # 注：daily 不带 OHLC（仅 close + volume），所以 ohlc 文件仅在 backfill 时生成。
    # 此处可选刷新 generated_at，但暂时保持不动以避免无意义 commit。

    # 更新 index
    index_path = out_dir / 'index.json'
    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding='utf-8'))
    else:
        idx = {'schema_version': '1.0', 'ohlc_codes': []}
    idx['generated_at'] = now
    idx['last_trade_date'] = today.isoformat()
    index_path.write_text(json.dumps(idx, ensure_ascii=False))
    log.info(f'daily done: indicators={len(indicators)} universe={len(universe)}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    run_daily_pipeline(
        holdings_dir=args.data_root / 'holdings',
        out_dir=args.data_root / 'stocks',
    )


if __name__ == '__main__':
    main()
