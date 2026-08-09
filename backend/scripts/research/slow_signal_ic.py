#!/usr/bin/env python
"""低频慢结构信号 IC 检验: strength/宽度 -> 未来收益的预测力.

日频四维 (收益/ARCH/横截面动量/周频) 已证接近随机. 这里检验慢变量是否有 alpha:
  1. 横截面 IC: cn_strength.composite 排名 <-> 未来 k 日收益排名 (k=1/5/20).
     项目"主题强弱映射"信号的直接 alpha 检验.
  2. 宽度择时: 市场宽度(站上MA20比率) -> 5日前瞻市场收益 + 超卖/超买分位条件收益.
IC>0 显著 = 信号有效; IC≈0 = 无 alpha (与日频结论一致).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from scipy.stats import pearsonr, spearmanr  # type: ignore[import-untyped]

sys.path.insert(0, os.path.dirname(__file__))
from ts_utils import SNAP, load_market_series, load_themes


def _dates() -> list[str]:
    return sorted(d for d in os.listdir(SNAP) if len(d) == 10 and d[4] == "-")


def load_strength_returns() -> tuple[list[str], np.ndarray, np.ndarray]:
    """日×主题 的 cn_strength.composite 与 r_1d 矩阵."""
    dates = _dates()
    th0 = load_themes(dates[0])
    n = len(th0)
    s = np.full((len(dates), n), np.nan)
    r = np.full((len(dates), n), np.nan)
    for i, d in enumerate(dates):
        th = load_themes(d)
        for j, t in enumerate(th):
            c = t.get("cn_strength", {}).get("composite")
            rv = t.get("returns", {}).get("r_1d")
            if c is not None:
                s[i, j] = float(c)
            if rv is not None:
                r[i, j] = float(rv)
    return dates, s, r


def forward_cum(r: np.ndarray, k: int) -> np.ndarray:
    """t 期的未来 k 日累计 log return = sum(r[t+1..t+k], axis=0). 无前视."""
    n = r.shape[0]
    f = np.full_like(r, np.nan)
    for t in range(n - k):
        f[t] = np.nansum(r[t + 1:t + 1 + k], axis=0)
    return f


def section1_ic() -> None:
    dates, s, r = load_strength_returns()
    print("=== ① 横截面 IC: cn_strength.composite -> 未来收益 (项目主题信号 alpha 检验) ===")
    print(f"{'horizon':>9}{'IC':>9}{'t-stat':>9}{'n':>6}  判定")
    for k in (1, 5, 20):
        f = forward_cum(r, k)
        ics = []
        for t in range(len(dates) - k):
            mask = ~(np.isnan(s[t]) | np.isnan(f[t]))
            if mask.sum() >= 5:
                rho, _ = spearmanr(s[t][mask], f[t][mask])
                ics.append(rho)
        ics = np.array(ics)
        ts = ics.mean() / (ics.std() / np.sqrt(len(ics))) if ics.std() > 0 else 0
        verdict = "有预测力*" if abs(ts) > 2 else "无预测力"
        print(f"{k:>7}日{ics.mean():>+9.4f}{ts:>+9.2f}{len(ics):>6}  {verdict}")


def section2_breadth() -> None:
    dates = _dates()
    # 宽度时序 (150日) 取自最后一个 snapshot 的 market_temperature
    # 温度/宽度时序只在真实归档 snapshot (cn-eod-archive) 有, backfill snapshot 不含.
    # 读 data/latest/market_temperature.json (最新真实归档, 含最近150日宽度).
    mt_path = os.path.join(os.path.dirname(SNAP), "latest", "market_temperature.json")
    with open(mt_path, encoding="utf-8") as f:
        mt = json.load(f)
    rate = mt["periods"]["ma20"]["market"]
    rd = {x["date"]: x["rate"] for x in rate if x.get("rate") is not None}
    _, rets, _ = load_market_series()  # 市场综合 r_1d (与 dates 对齐)
    width = np.array([rd.get(d, np.nan) for d in dates])
    k = 5
    fwd = np.array([rets[i + 1:i + 1 + k].sum() if i + k < len(rets) else np.nan
                    for i in range(len(rets))])
    mask = ~(np.isnan(width) | np.isnan(fwd))
    rr, pp = pearsonr(width[mask], fwd[mask])
    print("\n=== ② 市场宽度(站上MA20比率) -> 5日前瞻市场收益 ===")
    print(f"  Pearson r={rr:+.4f}  p={pp:.4f}  n={int(mask.sum())}")
    low = (width < 20) & mask
    high = (width > 80) & mask
    mid = ~low & ~high & mask
    print(f"  超卖(<20%): 后5日均收益 {fwd[low].mean():+.4f}  n={int(low.sum())}")
    print(f"  中性(20-80%):           {fwd[mid].mean():+.4f}  n={int(mid.sum())}")
    print(f"  超买(>80%):             {fwd[high].mean():+.4f}  n={int(high.sum())}")
    print("  (超卖反弹/超买回落 = 均值回归择时假设)")


if __name__ == "__main__":
    section1_ic()
    section2_breadth()
