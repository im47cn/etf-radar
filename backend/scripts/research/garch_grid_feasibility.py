"""GARCH 波动率 → 网格参数建议的可行性验证 — 预注册判据版.

动机: 5 年回测证实 87% 主题有 ARCH(波动率聚集), 但产品未用任何条件波动率信息。
若波动率可预测, 则网格间距可按预测波动率自适应 (而非固定 5%), 且 /evidence 页
可展示前瞻波动率。方向预测无效不妨碍波动率预测有效 — 两者统计上独立。

====================== 预注册判据(跑数前定死, 不做变体) ======================

设计:
- 评估日/样本与 grid_backtest.py 完全一致: 16 个评估日(步长60, 前向不重叠)
  × 30 主题; trailing 252 日拟合窗口; 前向 60 日检验。
- 三个预测器 (均为点时, 无前视):
    GARCH(1,1): trailing 252 日零均值正态 MLE (L-BFGS-B, α+β≤0.999),
                前向 1..60 日 σ² 路径平均 → sqrt。
    EWMA(λ=0.94): σ²_T 即预测 (鞅性质, 无需拟合)。
    RW (无条件基线): trailing 60 日样本 std。
- 已实现波动率: 前向 60 日日收益样本 std。

检验 A — 波动率可预测性(可行性核心):
- 损失 = QLIKE = σ²_r/σ²_f − ln(σ²_r/σ²_f) − 1, 逐 (评估日, 主题) 样本。
- 前向窗口互不重叠 → 配对 t 检验干净。
- 成功判据: GARCH 的 QLIKE 显著低于 RW (p<0.05)。
- 若 GARCH ≈ EWMA (p≥0.05) 但都优于 RW: 判"可行, 用更简单的 EWMA"。

检验 B — 网格参数改进(产品价值):
- 自适应间距 g_theme = clip(σ_daily_forecast × sqrt(20), 3%, 12%), GARCH 预测。
  (映射定死: 间距≈20日波动, 不调参)
- 对照: 固定 g=5% (现行 grid_backtest 口径), 同一价格路径, 成本 0.1%。
- premium = 网格终值 − 静态5050终值; 配对 (同路径) t 检验 adaptive − fixed。
- 成功判据: adaptive premium 显著 > fixed (p<0.05)。

判定规则:
- A✓B✓ → 可行: 建议落地 GARCH/EWMA 前瞻波动率 + 自适应网格参数
- A✓B✗ → 部分可行: 波动率可展示, 但间距自适应无增益, 不上参数建议
- A✗ → 不可行: 主题层日收益太脏(混合标的), 放弃, 不试变体

============================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize  # type: ignore[import-untyped]
from scipy.stats import ttest_1samp  # type: ignore[import-untyped]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
from compute_evidence import load_matrices
from grid_backtest import (
    GRID,
    HORIZON,
    MIN_FWD_DAYS,
    STEP,
    WINDOW,
    simulate_grid,
)

FORECAST_H = HORIZON  # 前向预测天数 = 检验窗口
SPACING_DAYS = 20     # 间距映射: g ≈ sqrt(20) 日波动
G_LO, G_HI = 0.03, 0.12
EWMA_LAM = 0.94


def fit_garch11(r: np.ndarray) -> tuple[float, float, float, float] | None:
    """零均值正态 GARCH(1,1) MLE。返回 (ω, α, β, σ²_T); 失败返回 None。"""
    r2 = r ** 2
    var0 = float(r2.mean())

    def nll(theta: np.ndarray) -> float:
        om, al, be = theta
        if om <= 0 or al < 0 or be < 0 or al + be >= 0.999:
            return 1e12
        s2 = var0
        ll = -0.5 * (np.log(2 * np.pi) + np.log(s2) + r2[0] / s2)
        for t in range(1, len(r2)):
            s2 = om + al * r2[t - 1] + be * s2
            if s2 <= 0:
                return 1e12
            ll += -0.5 * (np.log(2 * np.pi) + np.log(s2) + r2[t] / s2)
        return -float(ll)

    # 初值: 常见 GARCH 校准 (α=0.1, β=0.85, ω=var·(1−α−β))
    x0 = np.array([var0 * 0.05, 0.10, 0.85])
    res = minimize(nll, x0, method="L-BFGS-B",
                   bounds=[(1e-12, None), (0.0, 0.999), (0.0, 0.999)])
    if not res.success or res.fun >= 1e11:
        return None
    om, al, be = (float(v) for v in res.x)
    # 重算 σ²_T (用收敛参数)
    s2 = var0
    for t in range(1, len(r2)):
        s2 = om + al * r2[t - 1] + be * s2
    return om, al, be, s2


def garch_forecast_sigma(params: tuple[float, float, float, float], h: int) -> float:
    """未来 1..h 日 σ² 路径平均的 sqrt (persist: σ²_{T+k}=ω+(α+β)σ²_{T+k-1})."""
    om, al, be, s2 = params
    total, s = 0.0, s2
    for _ in range(h):
        s = om + (al + be) * s
        total += s
    return float(np.sqrt(total / h))


def ewma_sigma(r: np.ndarray) -> float:
    """EWMA(λ) 当前 σ (即无漂移预测)。"""
    lam = EWMA_LAM
    w = lam ** np.arange(len(r) - 1, -1, -1)
    return float(np.sqrt(np.sum(w * r ** 2) / np.sum(w)))


def qlike(sig_r: float, sig_f: float) -> float:
    """QLIKE 损失 (越低越好), σ²_r/σ²_f 比。"""
    ratio = (sig_r / sig_f) ** 2
    return float(ratio - np.log(ratio) - 1)


def main() -> None:
    data_root = Path(__file__).resolve().parents[3] / "data"
    dates, names, _display, _strength, returns = load_matrices(data_root)
    print(f"样本: {dates[0]} ~ {dates[-1]}, {len(dates)} 日 × {len(names)} 主题\n")

    recs: list[dict[str, float]] = []  # 逐 (评估日, 主题) 记录
    for t in range(WINDOW - 1, len(dates) - HORIZON, STEP):
        fwd = returns[t + 1:t + 1 + HORIZON]
        for j, tid in enumerate(names):
            win = returns[t - WINDOW + 1:t + 1, j]
            win = win[np.isfinite(win)]
            f = fwd[:, j]
            if len(win) < WINDOW * 0.9 or np.isfinite(f).sum() < MIN_FWD_DAYS:
                continue
            f_valid = f[np.isfinite(f)]
            sig_r = float(np.std(f_valid, ddof=1))  # 已实现 60 日波动
            if sig_r <= 0:
                continue
            params = fit_garch11(win)
            if params is None:
                continue
            sig_g = garch_forecast_sigma(params, FORECAST_H)
            sig_e = ewma_sigma(win[-60:])
            sig_w = float(np.std(win[-60:], ddof=1))  # RW: trailing 60 日
            if min(sig_g, sig_e, sig_w) <= 0:
                continue
            # 检验 B: 同一路径上 间距=clip(GARCH 20日波动) vs 固定 5%
            f_fill = f.copy()
            f_fill[~np.isfinite(f_fill)] = 0.0
            g_ad = float(np.clip(sig_g * np.sqrt(SPACING_DAYS), G_LO, G_HI))
            gv, sv = simulate_grid(f_fill, GRID)
            prem_fix = gv - sv
            gv, sv = simulate_grid(f_fill, g_ad)
            prem_ad = gv - sv
            recs.append({
                "date": float(t), "theme": float(j),
                "sig_r": sig_r, "sig_g": sig_g, "sig_e": sig_e, "sig_w": sig_w,
                "g_ad": g_ad, "prem_fix": prem_fix, "prem_ad": prem_ad,
            })
        print(f"  {dates[t]} 完成, 累计 {len(recs)} 样本")

    print(f"\n共 {len(recs)} 个 (评估日, 主题) 样本")

    # ---- 检验 A: QLIKE 配对 ----
    q_g = np.array([qlike(r["sig_r"], r["sig_g"]) for r in recs])
    q_e = np.array([qlike(r["sig_r"], r["sig_e"]) for r in recs])
    q_w = np.array([qlike(r["sig_r"], r["sig_w"]) for r in recs])
    t_gw = ttest_1samp(q_g - q_w, 0.0)
    t_ge = ttest_1samp(q_g - q_e, 0.0)
    t_ew = ttest_1samp(q_e - q_w, 0.0)
    print("\n[检验A] QLIKE (低=好):")
    print(f"  GARCH={q_g.mean():.4f}  EWMA={q_e.mean():.4f}  RW60={q_w.mean():.4f}")
    print(f"  GARCH vs RW : Δ={np.mean(q_g - q_w):+.4f}, t={t_gw.statistic:+.2f}, p={t_gw.pvalue:.4f}")
    print(f"  GARCH vs EWMA: Δ={np.mean(q_g - q_e):+.4f}, t={t_ge.statistic:+.2f}, p={t_ge.pvalue:.4f}")
    print(f"  EWMA vs RW  : Δ={np.mean(q_e - q_w):+.4f}, t={t_ew.statistic:+.2f}, p={t_ew.pvalue:.4f}")
    a_pass = bool(t_gw.pvalue < 0.05 and np.mean(q_g - q_w) < 0)

    # ---- 检验 B: 网格间距自适应 ----
    prem_ad = np.array([r["prem_ad"] for r in recs])
    prem_fix = np.array([r["prem_fix"] for r in recs])
    t_b = ttest_1samp(prem_ad - prem_fix, 0.0)
    gads = np.array([r["g_ad"] for r in recs])
    print("\n[检验B] 网格 premium (60日, 减静态5050):")
    print(f"  自适应间距 mean={prem_ad.mean():+.4%} (g 范围 {gads.min():.1%}~{gads.max():.1%}, 中位 {np.median(gads):.1%})")
    print(f"  固定5%    mean={prem_fix.mean():+.4%}")
    print(f"  Δ={np.mean(prem_ad - prem_fix):+.4%}, t={t_b.statistic:+.2f}, p={t_b.pvalue:.4f}")
    b_pass = bool(t_b.pvalue < 0.05 and np.mean(prem_ad - prem_fix) > 0)

    print("\n[预注册判定]")
    if a_pass and b_pass:
        print("  A✓B✓ → 可行: 前瞻波动率 + 自适应网格参数均值得落地")
    elif a_pass:
        print("  A✓B✗ → 部分可行: 波动率可展示/用于风控, 但间距自适应无增益, 不上参数建议")
        if t_ge.pvalue >= 0.05:
            print("  (GARCH≈EWMA: 落地时用更简单的 EWMA)")
    else:
        print("  A✗ → 不可行: 主题层日收益过脏, 放弃, 不试变体")


if __name__ == "__main__":
    main()
