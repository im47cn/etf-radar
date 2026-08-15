"""网格适合度(grid_fitness)判定的预测性回测 — 预注册判据版.

背景: 线上 signal_evidence.json 的 grid_fitness 是全样本(1212日)一次性计算,
属事后描述统计。本脚本做点时(point-in-time)验证: 在每个评估日用 trailing 窗口
复刻生产判定逻辑(compute_evidence.grid_fitness_per_theme 原函数直用), 然后前向
模拟网格策略, 检验判定是否有预测力。

====================== 预注册判据(跑数前定死, 不做变体) ======================

问题: t 日算出的 grid_score/verdict, 是否预测该主题 t+1..t+60 日的网格策略相对收益?

设计:
- 数据: data/snapshots/*/themes.json 的 returns.r_1d (1212 交易日 × ~30 主题)。
- 评估日: t ∈ [251, T-61], 步长 60 → 前向窗口互不重叠, 消除自相关。
- 点时判定: trailing 252 日窗口, 直接调生产函数 grid_fitness_per_theme
  (vol 0.40 + mean_reversion 0.35 + ARCH 0.25, hurst>0.55/trend 强制 marginal)。
- 网格策略(参数定死): 价格从 1.0 起始(日收益累乘), 50/50 股债初值,
  距上次再平衡价 ±5% 触发调回 50/50, 单边成本 0.1% (按成交额)。
- 对照基准: 同初值 50/50 静态持有(不调仓) — 同风险预算的公平 null。
- premium = 网格终值 − 静态5050终值 (60日)。
- 缺失日收益填 0 (该日无数据); 有效天数 < 48/60 的主题-日丢弃。

主检验(预注册为 primary, 因生产 suitable 结构性稀少——当前 1/29——组检验必欠功率):
- 每个评估日横截面 spearman(grid_score_t, premium_{t→t+60}) → IC 序列
- one-sample t 检验 H0: mean IC = 0
- 成功判据: mean IC > 0 且 p < 0.05

次检验(secondary, 仅当 suitable 样本 pooled ≥ 50 才解读):
- pooled Welch t: suitable premium vs unsuitable premium
- 逐日符号稳定性: (suitable均值 − unsuitable均值) > 0 的评估日占比 ≥ 60%

判定规则:
- 验证通过 = 主检验显著为正, 且次检验(如适用)方向一致
- 主检验 IC ≤ 0 或 p ≥ 0.05 → 结论"判定无预测力, 维持描述性定位", 不试变体

============================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr, ttest_1samp  # type: ignore[import-untyped]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 入 path
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ 入 path (复用生产函数)
from compute_evidence import grid_fitness_per_theme, load_matrices  # noqa: E402
from src.evidence.stats_utils import arch_per_theme  # noqa: E402

WINDOW = 252        # 点时判定 trailing 窗口
HORIZON = 60        # 前向模拟天数
STEP = 60           # 评估步长 = HORIZON, 前向窗口互不重叠
GRID = 0.05         # 网格间距 (±5% 触发再平衡)
COST = 0.001        # 单边成本 (按成交额)
MIN_FWD_DAYS = 48   # 前向窗口最低有效天数 (80%)


def simulate_grid(r_fwd: np.ndarray, grid: float = GRID) -> tuple[float, float]:
    """前向日收益 → (网格终值, 静态5050终值)。缺日填 0, 价格从 1.0 累乘。"""
    p = np.concatenate([[1.0], np.cumprod(1.0 + r_fwd)])
    shares = 0.5 / p[0]  # 初值 1.0, 50/50
    cash = 0.5
    ref = p[0]
    for price in p[1:]:
        if price >= ref * (1 + grid) or price <= ref * (1 - grid):
            value = cash + shares * price
            target_shares = 0.5 * value / price
            traded = abs(shares - target_shares) * price
            value -= traded * COST
            shares = 0.5 * value / price
            cash = 0.5 * value
            ref = price
    grid_v = cash + shares * p[-1]
    static_v = 0.5 + 0.5 * p[-1] / p[0]
    return grid_v, static_v


def main() -> None:
    data_root = Path(__file__).resolve().parents[3] / "data"
    dates, names, display, _strength, returns = load_matrices(data_root)
    n_dates = len(dates)
    print(f"样本: {dates[0]} ~ {dates[-1]}, {n_dates} 日 × {len(names)} 主题")

    rows: list[dict[str, object]] = []  # (date, theme) 样本
    eval_dates: list[str] = []
    for t in range(WINDOW - 1, n_dates - HORIZON, STEP):
        win = returns[t - WINDOW + 1:t + 1]
        arch = arch_per_theme(win, names)
        grid = grid_fitness_per_theme(win, names, display, arch, min_samples=100)
        verdicts = {e["theme_id"]: e for e in grid["themes"]}
        fwd = returns[t + 1:t + 1 + HORIZON]
        date_str = dates[t]
        eval_dates.append(date_str)
        for j, tid in enumerate(names):
            if tid not in verdicts:
                continue
            r_fwd = fwd[:, j].copy()
            if int(np.isfinite(r_fwd).sum()) < MIN_FWD_DAYS:
                continue
            r_fwd[~np.isfinite(r_fwd)] = 0.0
            grid_v, static_v = simulate_grid(r_fwd)
            rows.append({
                "date": date_str, "theme_id": tid,
                "verdict": verdicts[tid]["verdict"],
                "score": float(verdicts[tid]["grid_score"]),
                "premium": grid_v - static_v,
                "grid_v": grid_v, "static_v": static_v,
            })
        n_by = {v: sum(1 for r in rows if r["date"] == date_str and r["verdict"] == v)
                for v in ("suitable", "marginal", "unsuitable")}
        print(f"  {date_str}: 样本={len(verdicts)} {n_by}")

    print(f"\n共 {len(rows)} 个 (评估日, 主题) 样本, {len(eval_dates)} 个评估日")

    # ---- 次检验素材: 分 verdict 组的 premium ----
    by_verdict: dict[str, list[float]] = {}
    for r in rows:
        by_verdict.setdefault(str(r["verdict"]), []).append(float(r["premium"]))
    print("\n[描述] 分组 premium (网格 − 静态5050, 60日):")
    for v, vals in sorted(by_verdict.items()):
        arr = np.array(vals)
        print(f"  {v:11s}: n={len(arr):4d}  mean={arr.mean():+.4f}  median={np.median(arr):+.4f}")

    # ---- 主检验: 逐评估日 spearman(score, premium) → IC 序列 ----
    ics: list[float] = []
    print("\n[主检验] 逐日横截面 IC(spearman):")
    for d in eval_dates:
        day = [r for r in rows if r["date"] == d]
        if len(day) < 5:
            continue
        scores = np.array([float(r["score"]) for r in day])
        premiums = np.array([float(r["premium"]) for r in day])
        rho = float(spearmanr(scores, premiums).correlation)
        if not np.isnan(rho):
            ics.append(rho)
            print(f"  {d}: IC={rho:+.3f} (n={len(day)})")
    ic_arr = np.array(ics)
    t_stat, p_val = ttest_1samp(ic_arr, 0.0)
    print(f"\n  IC 序列: n={len(ic_arr)}  mean={ic_arr.mean():+.4f}  "
          f"t={t_stat:+.3f}  p={p_val:.4f}")

    # ---- 次检验: suitable vs unsuitable (仅当 suitable pooled ≥ 50) ----
    n_suitable = len(by_verdict.get("suitable", []))
    n_unsuit = len(by_verdict.get("unsuitable", []))
    secondary_msg = f"suitable n={n_suitable} < 50, 次检验不解读 (预注册规则)"
    if n_suitable >= 50 and n_unsuit >= 20:
        from scipy.stats import ttest_ind  # type: ignore[import-untyped]
        s = np.array(by_verdict["suitable"])
        u = np.array(by_verdict.get("unsuitable", []))
        tt = ttest_ind(s, u, equal_var=False)
        # 逐日符号稳定性
        signs = []
        for d in eval_dates:
            day = [r for r in rows if r["date"] == d]
            s_day = [float(r["premium"]) for r in day if r["verdict"] == "suitable"]
            u_day = [float(r["premium"]) for r in day if r["verdict"] == "unsuitable"]
            if s_day and u_day:
                signs.append(np.mean(s_day) - np.mean(u_day))
        pos_ratio = float(np.mean([s > 0 for s in signs])) if signs else float("nan")
        secondary_msg = (
            f"suitable({len(s)}) vs unsuitable({len(u)}): "
            f"mean {s.mean():+.4f} vs {u.mean():+.4f}, Welch t={tt.statistic:+.3f} p={tt.pvalue:.4f}; "
            f"逐日(suit−unsuit)>0 占比 {pos_ratio:.0%} (判据≥60%)"
        )
    print(f"\n[次检验] {secondary_msg}")

    # ---- 预注册判定 ----
    primary_pass = bool(ic_arr.mean() > 0 and p_val < 0.05)
    print("\n[预注册判定]")
    print(f"  主检验 (IC>0 且 p<0.05): {'通过' if primary_pass else '未通过'}")
    if primary_pass:
        print("  → grid_score 有真实预测力, 判定规则可用于提示; 次检验见上")
    else:
        print("  → 判定无预测力, 维持描述性定位, 不试变体 (预注册规则)")


if __name__ == "__main__":
    main()
