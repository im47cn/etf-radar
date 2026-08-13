#!/usr/bin/env python
"""预计算 signal_evidence.json: strength IC + 主题 ARCH, 供前端 /evidence 页.

仿 backfill_snapshots: 读 data/snapshots/*/themes.json 拼矩阵 -> 调
src.evidence.stats_utils 计算 -> atomic_write_json data/latest/signal_evidence.json.
IC/ARCH 是研究量, 月度 cron 跑 (不需每日).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 入 sys.path
from src.evidence.stats_utils import (
    acf,
    arch_per_theme,
    ic_by_horizon,
    rolling_ic_multi,
)
from src.output.writer import atomic_write_json


def load_matrices(
    data_root: Path,
) -> tuple[list[str], list[str], dict[str, str], np.ndarray, np.ndarray]:
    """读 snapshots 拼成 (dates, theme_ids, id->中文名, strength矩阵, return矩阵). 缺失填 nan."""
    snap = data_root / "snapshots"
    dates = sorted(d for d in os.listdir(snap) if len(d) == 10 and d[4] == "-")
    if not dates:
        raise SystemExit(f"无 snapshot: {snap}")
    with open(snap / dates[0] / "themes.json") as f:
        th0 = json.load(f)["themes"]
    names = [t["id"] for t in th0]
    display = {t["id"]: t.get("name", t["id"]) for t in th0}
    strength = np.full((len(dates), len(names)), np.nan)
    returns = np.full_like(strength, np.nan)
    for i, d in enumerate(dates):
        with open(snap / d / "themes.json") as f:
            th = json.load(f)["themes"]
        for j, t in enumerate(th):
            c = t.get("cn_strength", {}).get("composite")
            r = t.get("returns", {}).get("r_1d")
            if c is not None:
                strength[i, j] = float(c)
            if r is not None:
                returns[i, j] = float(r)
    return dates, names, display, strength, returns


def compute_evidence(data_root: Path, horizon: int = 20) -> dict[str, object]:
    dates, names, display, strength, returns = load_matrices(data_root)
    ic_horizon = ic_by_horizon(strength, returns)
    ic_rolling = rolling_ic_multi(strength, returns, dates, windows=(5, 20, 60), horizon=horizon)
    arch = arch_per_theme(returns, names)
    for e in arch:
        e["name"] = display.get(str(e["theme_id"]), str(e["theme_id"]))
    arch_sorted = sorted(arch, key=lambda e: float(e["r2_lb_p"]))
    # 全主题 r² ACF 衰减 (前端默认显示 is_arch=true + toggle 其余)
    idx = {n: i for i, n in enumerate(names)}
    rep_acf: dict[str, list[float]] = {}
    for tid, i in idx.items():
        col = returns[:, i]
        valid = col[np.isfinite(col)]
        if len(valid) > 15:
            rep_acf[tid] = [float(v) for v in acf(valid ** 2, 15)]
    # 逐季 ARCH 显著比例 (看波动率聚集随时间的变化). 每季 ~60 交易日, 下限放宽到 40 日
    # 以救回 56-59 日的"差一点"季; 最新未完整季 (如当前季) 例外——样本不足也保留, 因它代表
    # "当下", 缺失反而误导. 最新季内层下限降到 m+1=11 (技术下限), 输出 is_partial 标记.
    def quarter_of(date: str) -> str:
        return f"{date[:4]}-Q{(int(date[5:7]) - 1) // 3 + 1}"

    quarters = sorted({quarter_of(d) for d in dates})
    latest_q = quarter_of(dates[-1])
    arch_ts: list[dict[str, object]] = []
    for q in quarters:
        idxs = [i for i, d in enumerate(dates) if quarter_of(d) == q]
        is_latest = q == latest_q
        if not is_latest and len(idxs) < 40:
            continue
        # 最新季样本不足时降内层下限到 m+1; 其余季维持 40
        min_n = 11 if (is_latest and len(idxs) < 40) else 40
        arch_q = arch_per_theme(returns[idxs], names, min_samples=min_n)
        tested_q = len(arch_q)
        if tested_q == 0:
            continue
        n_arch_q = sum(1 for e in arch_q if e["is_arch"])
        arch_ts.append({
            "period": q, "arch_ratio": round(n_arch_q / tested_q, 3),
            "arch_count": n_arch_q, "tested": tested_q,
            "is_partial": bool(is_latest and len(idxs) < 40),
        })
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of_date": dates[-1],
        "sample": {"start": dates[0], "end": dates[-1], "n_days": len(dates)},
        "ic": {"rolling": ic_rolling, "by_horizon": ic_horizon},
        "arch": {
            "themes": arch_sorted,
            "summary": {
                "arch_count": int(sum(1 for e in arch if e["is_arch"])),
                "tested": len(arch),
                "expected_fp": round(0.05 * len(arch), 1),
            },
            "representative_acf": rep_acf,
            "time_series": arch_ts,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="预计算 signal_evidence.json (IC + ARCH)")
    ap.add_argument("--data-root", type=Path, default=Path("../data"))
    ap.add_argument("--horizon", type=int, default=20, help="IC forward 收益 horizon (日)")
    args = ap.parse_args()
    result = compute_evidence(args.data_root, horizon=args.horizon)
    out = args.data_root / "latest" / "signal_evidence.json"
    atomic_write_json(out, result)
    ic = result["ic"]
    arch = result["arch"]
    print(f"写入 {out}")
    print(f"样本: {result['sample']}")
    for e in ic["by_horizon"]:
        print(f"  IC({e['horizon']}d): mean={e['ic']:+.4f} t={e['t_stat']:+.2f} "
              f"range=[{e.get('ic_min')},{e.get('ic_max')}] recent={e.get('recent_ic')}")
    s = arch["summary"]
    print(f"ARCH: {s['arch_count']}/{s['tested']} (期望假阳性 {s['expected_fp']})")


if __name__ == "__main__":
    main()
