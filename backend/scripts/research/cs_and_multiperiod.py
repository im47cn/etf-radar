#!/usr/bin/env python
"""横截面分化度可预测性 + 多周期收益 ACF.

第一节: 分化度 cs_std 的真实周期 (lag5=周/lag21=月, 非上轮误称的 lag4=月度),
        + 横截面动量检验 (昨日强主题今日是否仍强 = 相对 alpha 基础).
第二节: r_5d/r_20d 多周期 ACF. 重叠窗口 ACF 虚高是假象, 须看 PACF + 非重叠采样.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from scipy.stats import spearmanr  # type: ignore[import-untyped]

sys.path.insert(0, os.path.dirname(__file__))
from ts_utils import SNAP, acf, ljung_box, load_matrix, load_themes, pacf

NL = 25


def _per_period_mean(field: str) -> np.ndarray:
    dates = sorted(d for d in os.listdir(SNAP) if len(d) == 10 and d[4] == "-")
    out = []
    for d in dates:
        th = load_themes(d)
        vs = [t.get("returns", {}).get(field) for t in th]
        vs = [v for v in vs if v is not None]
        out.append(float(np.mean(vs)) if vs else np.nan)
    return np.array(out)


def section1() -> None:
    _, _, m = load_matrix()
    cs = np.nanstd(m, axis=1)
    band = 1.96 / np.sqrt(len(cs))
    a, p = acf(cs, NL), pacf(cs, NL)
    print(f"=== ① 横截面分化度 cs_std (n={len(cs)}, 95%带±{band:.3f}) ===")
    sig = [(k, a[k], p[k]) for k in range(1, NL + 1) if abs(a[k]) > band or abs(p[k]) > band]
    print("  显著 lag:", ", ".join(f"lag{k}(ACF={ak:.2f},PACF={pk:.2f})"
                                    for k, ak, pk in sig) or "无")
    print(f"  lag5(周):  ACF={a[5]:.3f} PACF={p[5]:.3f}")
    print(f"  lag21(月): ACF={a[21]:.3f} PACF={p[21]:.3f}  <- 真正月度, 非上轮误称的 lag4")
    _, pv = ljung_box(cs, NL)
    print(f"  Ljung-Box(25) p={pv:.4f}")

    # 横截面动量: spearman(rank[t], rank[t+1])
    rhos = []
    for i in range(len(m) - 1):
        x, y = m[i], m[i + 1]
        mask = ~(np.isnan(x) | np.isnan(y))
        if mask.sum() >= 5:
            rho, _ = spearmanr(x[mask], y[mask])
            rhos.append(rho)
    rhos = np.array(rhos)
    t_stat = rhos.mean() / (rhos.std() / np.sqrt(len(rhos)))
    print("\n=== ② 横截面动量 ρ (昨日强→今日强, 相对 alpha 基础) ===")
    print(f"  mean ρ={rhos.mean():.4f}  std={rhos.std():.4f}  t={t_stat:.2f}  n={len(rhos)}")
    print(f"  -> {'显著正: 横截面动量存在 (相对 alpha 有统计基础)' if t_stat > 2 else '不显著'}")
    med = np.median(cs[:-1])
    hi = rhos[cs[:-1] >= med]
    lo = rhos[cs[:-1] < med]
    print(f"  调节效应: 高分化日 ρ={hi.mean():.4f}(n={len(hi)}) "
          f"vs 低分化日 ρ={lo.mean():.4f}(n={len(lo)})")


def section2() -> None:
    r5 = _per_period_mean("r_5d")
    r20 = _per_period_mean("r_20d")
    print("\n=== ③ 多周期收益 ACF (警告: 重叠窗口!) ===")
    print("  r_5d/r_20d 相邻日共享 4/5、19/20 数据, ACF 虚高是数学假象, 须看 PACF + 非重叠.\n")
    for name, x in [("r_5d", r5), ("r_20d", r20)]:
        x = x[~np.isnan(x)]
        a, p = acf(x, NL), pacf(x, NL)
        _, pv = ljung_box(x, NL)
        print(f"  {name} (n={len(x)}):")
        print(f"    ACF[1-5] = {[round(float(a[k]), 2) for k in range(1, 6)]}  (重叠假象)")
        print(f"    PACF[1-5]= {[round(float(p[k]), 2) for k in range(1, 6)]}  (可信)")
        print(f"    Ljung-Box p={pv:.4f}")
    # 非重叠 r_5d: 每5日采样一个 (相邻不重叠)
    nr5 = r5[::5]
    nr5 = nr5[~np.isnan(nr5)]
    nl = min(NL, max(3, len(nr5) // 4))
    if len(nr5) > 10:
        a, p = acf(nr5, nl), pacf(nr5, nl)
        _, pv = ljung_box(nr5, nl)
        print(f"\n  r_5d 非重叠采样 (每5日, n={len(nr5)}):")
        print(f"    ACF[1-5] = {[round(float(a[k]), 2) for k in range(1, min(6, nl + 1))]}")
        print(f"    PACF[1-5]= {[round(float(p[k]), 2) for k in range(1, min(6, nl + 1))]}")
        print(f"    Ljung-Box(m={nl}) p={pv:.4f}  -> {'非白噪' if pv < 0.05 else '白噪'}")
    else:
        print(f"\n  r_5d 非重叠样本 n={len(nr5)} 太少, 无法检验")


if __name__ == "__main__":
    section1()
    section2()
