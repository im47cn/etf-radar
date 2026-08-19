"""金银比(GSR)择时预注册回测 — 判据先定死, 跑数后不变体.

背景: /metals 页规划中的"金银比历史分位"拟作描述性指标。民间假设:
金银比极端高位 = 金贵银贱 = 白银相对黄金被低估 → 未来白银跑赢黄金(均值回归)。
本脚本点时(point-in-time)验证该假设是否含有 alpha, 决定指标是纯展示还是可上信号。

====================== 预注册判据(跑数前定死, 不做变体) ======================

数据: GLD/SLV 复权日收盘 2006-04-28..2026-08-19 (5109 交易日, yfinance 拉取)。
  ratio_t = GLD_t / SLV_t。ETF 比值与真实金银比差一个常数乘数, 分位统计不受影响。

信号: pct_t = ratio_t 在 trailing 1260 日(5y)窗口内的分位; 前 1260 日 burn-in 丢弃
  → 有效评估自 2011-04 起, 覆盖 2011 白银顶点后的完整周期。

评估日与窗口:
  - 主窗口 h=60, 步长 60 → 前向窗口互不重叠, 普通 t 检验
  - 次窗口 h=20, 步长 5 → 重叠样本, Newey-West(lag=20), 仅描述不判定

前向收益: excess_{t,h} = SLV[t,t+h] 收益 − GLD[t,t+h] 收益 (白银相对黄金)。

主检验(primary, 唯一成功判据):
  按 pct_t 分五分位桶 Q1(低)..Q5(高金银比):
    C1: Q5 桶 mean excess(60d) > 0 且 one-sample t p < 0.05
    C2: Q5 mean − Q1 mean > 0
  成功 = C1 ∧ C2。经济意义附加条件(描述性): Q5 mean > 0.2% (2×单边 0.1% 换仓成本)。

次检验(secondary, 仅描述, 不参与判定):
  - h=20 各桶均值 (NW t)
  - 绝对收益版 (SLV 收益, 对照"白银自身有 beta"的混淆解释)
  - Q1 对称方向 (低金银比 → 白银跑输?)
  - 前后半样本符号稳定性

判定失败 → 金银比分位维持纯描述性指标(与 leader 规则同处理)。
"""
from __future__ import annotations

import numpy as np
from scipy.stats import ttest_1samp  # type: ignore[import-untyped]

BURN_IN = 1260  # 5y trailing 分位窗口
HORIZONS = {60: 60, 20: 5}  # h -> 步长
QUANTILES = 5
COST_ROUNDTRIP = 0.002  # 2×0.1% 单边


def fetch_closes() -> tuple[np.ndarray, np.ndarray]:
    """GLD/SLV 复权日收盘, 按日期对齐 dropna."""
    import yfinance as yf

    d = yf.download(["GLD", "SLV"], start="2006-01-01", progress=False, auto_adjust=True)
    c = d["Close"].dropna()
    return c["GLD"].to_numpy(), c["SLV"].to_numpy()


def rolling_percentile(x: np.ndarray, window: int) -> np.ndarray:
    """每个时点, 当前值在 trailing window 内的分位 (含自身)."""
    out = np.full(len(x), np.nan)
    for i in range(window - 1, len(x)):
        w = x[i - window + 1 : i + 1]
        out[i] = float((w <= w[-1]).mean())
    return out


def forward_return(x: np.ndarray, h: int, ts: np.ndarray) -> np.ndarray:
    """ts 评估日索引处的前向 h 日收益 (末尾不足 h 日的位置为 nan)."""
    out = np.full(len(ts), np.nan)
    for k, t in enumerate(ts):
        if t + h < len(x):
            out[k] = x[t + h] / x[t] - 1.0
    return out


def nw_tstat(x: np.ndarray, lag: int) -> float:
    """均值 ≠ 0 的 Newey-West t 统计量 (重叠样本用)."""
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 3:
        return float("nan")
    e = x - x.mean()
    lrv = float(e @ e) / n
    for l in range(1, min(lag, n - 1) + 1):
        gamma = float(e[l:] @ e[:-l]) / n
        lrv += 2.0 * (1.0 - l / (lag + 1)) * gamma
    return float(x.mean() / np.sqrt(max(lrv, 1e-18) / n))


def bucket_stats(pct: np.ndarray, excess: np.ndarray, label: str) -> list[tuple[str, int, float, float]]:
    """按分位五分桶, 返回 (桶名, n, mean, t) 列表. t 为普通 one-sample."""
    rows: list[tuple[str, int, float, float]] = []
    qs = np.nanquantile(pct, np.linspace(0, 1, QUANTILES + 1))
    for b in range(QUANTILES):
        if b < QUANTILES - 1:
            m = (pct >= qs[b]) & (pct < qs[b + 1])
        else:
            m = (pct >= qs[b]) & (pct <= qs[b + 1])
        v = excess[m]
        v = v[~np.isnan(v)]
        t = float(ttest_1samp(v, 0.0).statistic) if len(v) > 2 else float("nan")
        rows.append((f"Q{b + 1}", len(v), float(v.mean()), t))
    print(f"\n[{label}] 五分位桶 (桶内均值, t): " + ", ".join(f"{n}:{m * 100:.2f}%({t:.1f})" for _, n, m, t in rows))
    return rows


def main() -> None:
    gld, slv = fetch_closes()
    ratio = gld / slv
    pct = rolling_percentile(ratio, BURN_IN)
    valid = np.where(~np.isnan(pct))[0]
    print(f"样本: {len(gld)} 交易日, 有效评估区间 idx {valid[0]}..{valid[-1]}")

    results: dict[int, dict[str, np.ndarray]] = {}
    for h, step in HORIZONS.items():
        ts = np.arange(valid[0], len(ratio) - h, step)
        ex = forward_return(slv, h, ts) - forward_return(gld, h, ts)
        abs_s = forward_return(slv, h, ts)
        results[h] = {"ts": ts, "pct": pct[ts], "ex": ex, "abs": abs_s}

    # ---- 主检验: h=60 不重叠 ----
    r = results[60]
    rows = bucket_stats(r["pct"], r["ex"], "主检验 h=60 白银-黄金超额")
    q5 = next(x for x in rows if x[0] == "Q5")
    q1 = next(x for x in rows if x[0] == "Q1")
    p5 = float(ttest_1samp(r["ex"][r["pct"] >= np.nanquantile(r["pct"], 0.8)], 0.0).pvalue)
    c1 = q5[2] > 0 and p5 < 0.05
    c2 = q5[2] > q1[2]
    print(f"\nC1 Q5均值>0 且 p<0.05: {q5[2] * 100:+.2f}%, p={p5:.4f} → {'✓' if c1 else '✗'}")
    print(f"C2 Q5>Q1: {q5[2] * 100:+.2f}% vs {q1[2] * 100:+.2f}% → {'✓' if c2 else '✗'}")
    print(f"经济意义: Q5均值 vs 换仓成本 {COST_ROUNDTRIP * 100:.1f}% → {'有' if q5[2] > COST_ROUNDTRIP else '无(幅度不覆盖成本)'}")
    print(f"★ 主判定: {'有 alpha' if (c1 and c2) else '无 alpha, 金银比分位维持描述性'}")

    # ---- 次检验: h=20 (NW, 仅描述) ----
    r2 = results[20]
    bucket_stats(r2["pct"], r2["ex"], "次检验 h=20 超额 (t 为普通值, 显著性看整体 NW)")
    m5 = r2["ex"][r2["pct"] >= np.nanquantile(r2["pct"], 0.8)]
    m5 = m5[~np.isnan(m5)]
    print(f"h=20 Q5 NW t={nw_tstat(m5, 20):.2f}")

    # 绝对收益混淆检查
    r3 = results[60]
    bucket_stats(r3["pct"], r3["abs"], "h=60 白银绝对收益 (区分 beta vs 相对 alpha)")

    # 前后半样本稳定性
    half = len(r["ts"]) // 2
    for name, seg in [("前半", slice(0, half)), ("后半", slice(half, None))]:
        seg_pct, seg_ex = r["pct"][seg], r["ex"][seg]
        q5m = seg_ex[seg_pct >= np.nanquantile(seg_pct, 0.8)]
        q5m = q5m[~np.isnan(q5m)]
        print(f"稳定性 {name}: Q5 超额均值 {q5m.mean() * 100:+.2f}% (n={len(q5m)})")


if __name__ == "__main__":
    main()
