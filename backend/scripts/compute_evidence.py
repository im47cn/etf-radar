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
from typing import cast

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 入 sys.path
from src.evidence.scorecard import SignalEvent, scorecard_rows
from src.evidence.stats_utils import (
    acf,
    annualized_volatility,
    arch_per_theme,
    forecast_vol_annualized,
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


# 趋势护栏阈值: 近 60/120 交易日累计涨跌幅 (对称) 任一超限即判定强趋势 regime.
# 全样本 Hurst 是 5 年均值, 对近期单边钝感 (实证: 中概互联 ytd -28% 但 H=0.498 未触发护栏).
TREND_LIMIT_60 = 0.10
TREND_LIMIT_120 = 0.15


def _round_opt(v: float | None, nd: int = 4) -> float | None:
    """可选浮点四舍五入, None 透传."""
    return None if v is None else round(v, nd)


def recent_cum_return(col: np.ndarray, window: int = 120, min_tail: int = 60) -> float | None:
    """尾部 window 日累计收益 (几何累乘). 有效值 <min_tail 返回 None."""
    valid = col[np.isfinite(col)]
    if len(valid) < min_tail:
        return None
    tail = valid[-window:]
    return float(np.prod(1.0 + tail) - 1.0)


def trend_regime(ret_60: float | None, ret_120: float | None) -> str | None:
    """近期强趋势判定: |r_60d|≥10% 或 |r_120d|≥15% -> 'down'/'up', 否则 None (震荡)."""
    for r, lim in ((ret_60, TREND_LIMIT_60), (ret_120, TREND_LIMIT_120)):
        if r is not None and abs(r) >= lim:
            return "down" if r < 0 else "up"
    return None


def grid_fitness_per_theme(
    returns: np.ndarray, names: list[str], display: dict[str, str],
    arch_results: list[dict[str, object]], min_samples: int = 100,
) -> dict[str, object]:
    """每主题网格适配度复合分: 波动率(0.40) + 均值回归Hurst(0.35) + ARCH持续(0.25).

    三维度跨主题 percentile rank 归一化后加权. Hurst/min_samples 不足的主题计入 skipped.
    verdict: suitable(≥0.65)/marginal(0.40-0.65)/unsuitable(<0.40);
    Hurst>0.55 或近期强趋势 (trend_regime) 强制降 marginal.
    """
    arch_p = {str(e["theme_id"]): float(e["r2_lb_p"]) for e in arch_results}
    weights = {"vol": 0.40, "mean_reversion": 0.35, "arch": 0.25}
    raw: list[dict[str, object]] = []
    for j in range(returns.shape[1]):
        col = returns[:, j]
        valid = col[np.isfinite(col)]
        n = len(valid)
        tid = names[j]
        if n < min_samples:
            continue
        vol = annualized_volatility(col)
        h = hurst_exponent(col)
        p = arch_p.get(tid)
        if vol is None or h is None or p is None:
            continue
        r60 = recent_cum_return(col, window=60)
        r120 = recent_cum_return(col, window=120)
        nlp = float(-np.log10(p)) if 0.0 < p < 1.0 else 0.0
        # GARCH(1,1) 前瞻 60 日年化波动 (QLIKE 验证优于无条件基线, 见 stats_utils 注释)
        fv = forecast_vol_annualized(col, horizon=60)
        raw.append({
            "theme_id": tid, "name": display.get(tid, tid), "n": n,
            "ann_vol": float(vol), "hurst": float(h),
            "arch_neg_log10p": nlp, "mr_signal": max(0.0, 0.5 - float(h)),
            "ret_60d": r60, "ret_120d": r120, "trend": trend_regime(r60, r120),
            "vol_forecast": fv,
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
        trend = r["trend"]
        if h > 0.55 or trend is not None:
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
            "vol_forecast_ann": _round_opt(cast("float | None", r["vol_forecast"])),
            "arch_neg_log10p": round(float(r["arch_neg_log10p"]), 2),
            "ret_60d": _round_opt(cast("float | None", r["ret_60d"])),
            "ret_120d": _round_opt(cast("float | None", r["ret_120d"])),
            "trend_regime": trend,
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


def load_signal_events(data_root: Path) -> tuple[list[str], list[SignalEvent]]:
    """读 snapshots 拼逐日信号事件序列 (口径同 scripts/research/resonance_conditions).

    方向 = 信号日 theme.returns.r_1d 符号 (美股动量代理), 结果 = 下一 snapshot 的
    trigger_cn_etf 的 r_1d 符号是否同向; 任一缺失/为 0 (方向无定义) 的事件丢弃.
    """
    snap = data_root / "snapshots"
    dates = sorted(d for d in os.listdir(snap) if len(d) == 10 and d[4] == "-")
    theme_r1: list[dict[str, float | None]] = []
    etf_r1: list[dict[str, float | None]] = []
    raw: list[tuple[int, str, str, str]] = []  # (day_index, signal, theme_id, code)
    for i, d in enumerate(dates):
        with open(snap / d / "themes.json") as f:
            theme_r1.append({t["id"]: t.get("returns", {}).get("r_1d") for t in json.load(f)["themes"]})
        etf_path = snap / d / "etfs.json"
        if etf_path.exists():  # 个别历史 snapshot 可能缺 etfs/signals
            with open(etf_path) as f:
                etf_r1.append({e["code"]: (e.get("returns") or {}).get("r_1d")
                               for e in json.load(f)["etfs"]})
        else:
            etf_r1.append({})
        sig_path = snap / d / "signals.json"
        if not sig_path.exists():
            continue
        with open(sig_path) as f:
            ts = json.load(f).get("theme_signals", [])
        for s in ts:
            code = s.get("trigger_cn_etf")
            if s.get("signal") in ("resonance", "transmission") and code:
                raw.append((i, str(s["signal"]), str(s["theme_id"]), str(code)))
    events: list[SignalEvent] = []
    for i, signal, theme_id, code in raw:
        m = theme_r1[i].get(theme_id)
        nxt = etf_r1[i + 1].get(code) if i + 1 < len(dates) else None
        if m is None or m == 0.0 or nxt is None:
            continue
        events.append(SignalEvent(i, signal, theme_id, float(m), float(nxt)))
    return dates, events


def compute_evidence(data_root: Path, horizon: int = 20) -> dict[str, object]:
    dates, names, display, strength, returns = load_matrices(data_root)
    _, events = load_signal_events(data_root)
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
        # 信号计分卡: resonance/transmission 近 60/120 交易日胜率 vs 长期基线
        "scorecard": scorecard_rows(events, len(dates)),
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
