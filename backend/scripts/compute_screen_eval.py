#!/usr/bin/env python
"""预计算 screen_eval.json: SEPA candidates 池复盘 (口径 B 突破事件), 供 /evidence 页.

口径: candidate 在 snapshots/*/trading.json 首次出现日 = 入池日; 入池后 MAX_WAIT_DAYS
内首次收盘 >=pivot 且非一字涨停 = 突破事件; R = (exit−entry)/(entry−stop), exit = 突破日
后第 20 根收盘; T+N (N∈{5,20}) 与基准 000985 同窗口超额同步输出. 详见 issue #60 与
src/evidence/screen_eval.py 模块头.

读 data/snapshots/*/trading.json + data/stocks/ohlcv/{code}.json (纯离线, 固定输入→
固定输出) → atomic_write_json data/latest/screen_eval.json. 复盘是研究量, 月度 cron 跑
(不需每日); 调度接入拆人类 PR 并入 evidence-monthly.yml (不触 .github/).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 入 sys.path
from src.evidence.screen_eval import (
    MIN_N,
    T_HORIZONS,
    Candidate,
    Outcome,
    bucket_rows,
    evaluate_candidate,
    hit_ci,
)
from src.output.writer import atomic_write_json
from src.trading.environment import RS_BENCHMARK

BJT = ZoneInfo('Asia/Shanghai')


def _trading_snapshots(data_root: Path) -> list[tuple[str, Path]]:
    """枚举含 trading.json 的日期快照 (升序; 枚举法同 compute_evidence)."""
    snap = data_root / 'snapshots'
    if not snap.exists():
        return []
    out: list[tuple[str, Path]] = []
    for d in sorted(x for x in os.listdir(snap) if len(x) == 10 and x[4] == '-'):
        p = snap / d / 'trading.json'
        if p.exists():
            out.append((d, p))
    return out


def load_candidates(data_root: Path) -> list[Candidate]:
    """candidates 首次出现日 = 入池日; 此后重复出现去重 (每 code 恰一事件, 不读 generated_at).

    字段映射: stop_at_pool <- trading.json 'stop'; vcp_quality <- 嵌套键 vcp.quality.
    """
    seen: set[str] = set()
    out: list[Candidate] = []
    for d, p in _trading_snapshots(data_root):
        with open(p) as f:
            doc = json.load(f)
        for c in doc.get('candidates', []):
            code = str(c['code'])
            if code in seen:
                continue
            seen.add(code)
            out.append(Candidate(
                code=code, pool_date=d, pivot=float(c['pivot']), stop=float(c['stop']),
                composite_score=float(c['composite_score']), rs_pct=float(c['rs_pct']),
                vcp_quality=float(c['vcp']['quality']), state=str(c['state']),
            ))
    return out


def load_bars(data_root: Path, code: str) -> list[dict[str, Any]]:
    """读个股/基准 ohlcv bars (已按日期升序); 文件缺失返回 [] (上层归 missing_quotes)."""
    p = data_root / 'stocks' / 'ohlcv' / f'{code}.json'
    if not p.exists():
        return []
    with open(p) as f:
        return list(json.load(f).get('bars', []))


def benchmark_returns(bench_bars: list[dict[str, Any]], event_date: str, n: int) -> float | None:
    """基准同窗口 T+n 收益: 定位首个 d>=event_date 的下标 k, 取 bars[k+n]/bars[k]−1.

    无对齐点 (事件日晚于基准末根) 或 k+n 越界 → None.
    """
    k = next((i for i, b in enumerate(bench_bars) if str(b['d']) >= event_date), None)
    if k is None or k + n >= len(bench_bars):
        return None
    return float(bench_bars[k + n]['c']) / float(bench_bars[k]['c']) - 1.0


def compute_screen_eval(data_root: Path) -> dict[str, object]:
    """全量复盘: 快照 candidates + 离线 ohlcv → screen_eval dict (结构写死于 plan)."""
    candidates = load_candidates(data_root)
    snapshots = _trading_snapshots(data_root)
    bench_bars = load_bars(data_root, RS_BENCHMARK)

    pairs: list[tuple[Candidate, Outcome]] = []
    n_missing = 0
    for cand in candidates:
        bars = load_bars(data_root, cand.code)
        outcome = evaluate_candidate(cand, bars) if bars else Outcome(status='missing_quotes')
        if outcome.status == 'missing_quotes':
            n_missing += 1
        pairs.append((cand, outcome))

    # 事件收益 + 基准对齐超额 (excess_N = ret_N − benchmark T+N); 基准不可用 → 全部 None
    r_values: list[float] = []
    rets_by_n: dict[int, list[float]] = {n: [] for n in T_HORIZONS}
    excess_by_n: dict[int, list[float]] = {n: [] for n in T_HORIZONS}
    for _, o in pairs:
        if o.status != 'broke_out':
            continue
        if o.r_multiple is not None:
            r_values.append(o.r_multiple)
        for n in T_HORIZONS:
            r = o.ret_5d if n == 5 else o.ret_20d
            if r is None:
                continue
            rets_by_n[n].append(r)
            if bench_bars and o.event_date is not None:
                b = benchmark_returns(bench_bars, o.event_date, n)
                if b is not None:
                    excess_by_n[n].append(r - b)

    def _median(xs: list[float]) -> float | None:
        return round(float(np.median(xs)), 4) if xs else None

    n_broke = sum(1 for _, o in pairs if o.status == 'broke_out')
    n_never = sum(1 for _, o in pairs if o.status == 'never_broke_out')
    n_pending = sum(1 for _, o in pairs if o.status == 'pending')
    denom = n_broke + n_never
    return {
        'schema_version': '1.0',
        'generated_at': datetime.now(UTC).astimezone(BJT).isoformat(),
        'as_of_date': snapshots[-1][0] if snapshots else None,
        'sample': {
            'first_pool_date': candidates[0].pool_date if candidates else None,
            'last_pool_date': candidates[-1].pool_date if candidates else None,
            'n_snapshots': len(snapshots),
            'n_candidates': len(candidates),
        },
        'events': {
            'total': len(pairs),
            'broke_out': n_broke,
            'never_broke_out': n_never,
            'pending': n_pending,
            'missing_quotes': n_missing,
            'breakout_rate': round(n_broke / denom, 4) if denom else 0.0,
            'breakout_rate_status': 'insufficient' if denom < MIN_N else 'ok',
        },
        'returns': {**hit_ci(r_values), 'median_excess_20d': _median(excess_by_n[20])},
        'by_t': [
            {
                'horizon': n,
                'n': len(rets_by_n[n]),
                'mean_ret': round(float(np.mean(rets_by_n[n])), 4) if rets_by_n[n] else None,
                'median_excess': _median(excess_by_n[n]),
            }
            for n in T_HORIZONS
        ],
        'buckets': bucket_rows(pairs),
        'benchmark': {
            'code': RS_BENCHMARK,
            'status': 'ok' if bench_bars else 'unavailable',
            'as_of': str(bench_bars[-1]['d']) if bench_bars else None,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description='预计算 screen_eval.json (candidates 池复盘, 口径 B)')
    ap.add_argument('--data-root', type=Path, default=Path('../data'))
    args = ap.parse_args()
    result = compute_screen_eval(args.data_root)
    out = args.data_root / 'latest' / 'screen_eval.json'
    atomic_write_json(out, result)
    ev = result['events']
    print(f'写入 {out}')
    print(f"events: total={ev['total']} broke_out={ev['broke_out']} never_broke_out="
          f"{ev['never_broke_out']} pending={ev['pending']} missing_quotes={ev['missing_quotes']}")


if __name__ == '__main__':
    main()
