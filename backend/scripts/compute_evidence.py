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
    annualized_volatility,
    arch_per_theme,
    hurst_exponent,
    ic_by_horizon,
    percentile_rank,
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


def grid_fitness_per_theme(
    returns: np.ndarray, names: list[str], display: dict[str, str],
    arch_results: list[dict[str, object]], min_samples: int = 100,
) -> dict[str, object]:
    """每主题网格适配度复合分: 波动率(0.40) + 均值回归Hurst(0.35) + ARCH持续(0.25).

    三维度跨主题 percentile rank 归一化后加权. Hurst/min_samples 不足的主题计入 skipped.
    verdict: suitable(≥0.65)/marginal(0.40-0.65)/unsuitable(<0.40); Hurst>0.55 强制降 marginal.
    """
    arch_p = {str(e["theme_id"]): float(e["r2_lb_p"]) for e in arch_results}
    weights = {"vol": 0.40, "mean_reversion": 0.35, "arch": 0.25}
    raw: list[dict[str, object]] = []
    for j in range(returns.shape[1]):
        col = returns[:, j]
        valid = col[np.isfinite(col)]
        n = int(len(valid))
        tid = names[j]
        if n < min_samples:
            continue
        vol = annualized_volatility(col)
        h = hurst_exponent(col)
        p = arch_p.get(tid)
        if vol is None or h is None or p is None:
            continue
        nlp = float(-np.log10(p)) if 0.0 < p < 1.0 else 0.0
        raw.append({
            "theme_id": tid, "name": display.get(tid, tid), "n": n,
            "ann_vol": float(vol), "hurst": float(h),
            "arch_neg_log10p": nlp, "mr_signal": max(0.0, 0.5 - float(h)),
        })
    skipped = int(returns.shape[1]) - len(raw)
    if not raw:
        return {"themes": [], "summary": {"tested": 0, "skipped": skipped,
                "suitable_count": 0, "median_score": 0.0}, "weights": weights}
    vols = [float(r["ann_vol"]) for r in raw]
    mrs = [float(r["mr_signal"]) for r in raw]
    archs = [float(r["arch_neg_log10p"]) for r in raw]
    themed: list[dict[str, object]] = []
    for r in raw:
        pct_vol = percentile_rank(vols, float(r["ann_vol"]))
        pct_mr = percentile_rank(mrs, float(r["mr_signal"]))
        pct_arch = percentile_rank(archs, float(r["arch_neg_log10p"]))
        score = 0.40 * pct_vol + 0.35 * pct_mr + 0.25 * pct_arch
        h = float(r["hurst"])
        if h > 0.55:
            verdict = "marginal"
        elif score >= 0.65:
            verdict = "suitable"
        elif score >= 0.40:
            verdict = "marginal"
        else:
            verdict = "unsuitable"
        themed.append({
            "theme_id": r["theme_id"], "name": r["name"], "n": r["n"],
            "ann_vol": round(float(r["ann_vol"]), 4), "hurst": round(h, 3),
            "arch_neg_log10p": round(float(r["arch_neg_log10p"]), 2),
            "pct_vol": round(pct_vol, 3), "pct_mean_reversion": round(pct_mr, 3),
            "pct_arch": round(pct_arch, 3), "grid_score": round(score, 3),
            "verdict": verdict,
        })
    themed.sort(key=lambda e: float(e["grid_score"]), reverse=True)
    scores = [float(e["grid_score"]) for e in themed]
    return {
        "themes": themed,
        "summary": {
            "tested": len(themed), "skipped": skipped,
            "suitable_count": sum(1 for e in themed if e["verdict"] == "suitable"),
            "median_score": round(float(np.median(scores)), 3),
        },
        "weights": weights,
    }


def compute_evidence(data_root: Path, horizon: int = 20) -> dict[str, object]:
    dates, names, display, strength, returns = load_matrices(data_root)
    ic_horizon = ic_by_horizon(strength, returns)
    ic_rolling = rolling_ic_multi(strength, returns, dates, windows=(5, 20, 60), horizon=horizon)
    arch = arch_per_theme(returns, names)
    for e in arch:
        e["name"] = display.get(str(e["theme_id"]), str(e["theme_id"]))
    arch_sorted = sorted(arch, key=lambda e: float(e["r2_lb_p"]))
    # 网格适配度复合分 (波动率 + Hurst 均值回归 + ARCH 持续), 跨主题 percentile rank 加权
    grid = grid_fitness_per_theme(returns, names, display, arch)
    # 全主题 r² ACF 衰减 (前端默认显示 is_arch=true + toggle 其余)
    idx = {n: i for i, n in enumerate(names)}
    rep_acf: dict[str, list[float]] = {}
    for tid, i in idx.items():
        col = returns[:, i]
        valid = col[np.isfinite(col)]
        if len(valid) > 15:
            rep_acf[tid] = [float(v) for v in acf(valid ** 2, 15)]
    # ARCH 显著比例滚动时序 (120 日窗口, 按月步进): 每点 n≈120 功效充足, 给出可比的
    # 强度时序, 而非被功率压扁的日历季绝对值 (日历季 n≈40-66 严重欠功率, 见 CONVENTIONS).
    # 窗口右端 = 该月最后交易日, 向前 120 日; 早期不足 120 日的月跳过.
    months = sorted({d[:7] for d in dates})
    arch_ts: list[dict[str, object]] = []
    for m_str in months:
        end_idx = max(i for i, d in enumerate(dates) if d[:7] == m_str)
        if end_idx < 119:  # 向前凑不满 120 日, 跳过早期月
            continue
        arch_m = arch_per_theme(returns[end_idx - 119:end_idx + 1], names)
        tested_m = len(arch_m)
        if tested_m == 0:
            continue
        n_arch_m = sum(1 for e in arch_m if e["is_arch"])
        arch_ts.append({
            "period": m_str, "arch_ratio": round(n_arch_m / tested_m, 3),
            "arch_count": n_arch_m, "tested": tested_m,
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
        "grid_fitness": grid,
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
