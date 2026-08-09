#!/usr/bin/env python
"""事件研究 (极端日均值回归) + 个股层 ARCH/动量 (主题ETF抹平的结构).

第一节 (themes, 日频唯一可能藏信号的非线性处):
  - 横截面短期反转: t日 top3/bottom3 主题 -> t+1 收益 (正差=反转)
  - 时序极端日 (|z|>1.5) 次日收益
第二节 (stocks 5542只×150日, 全算):
  - 个股 ARCH 比例 (对比主题 13%, 看ETF是否抹平了个股波动率聚集)
  - 全市场横截面 ρ (对比主题 ≈0, 看经典个股短期反转是否存在)
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from scipy.stats import spearmanr  # type: ignore[import-untyped]

sys.path.insert(0, os.path.dirname(__file__))
from ts_utils import ljung_box, load_market_series, load_matrix

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
NLAGS = 15


def section1_event() -> None:
    _, _, r = load_matrix()
    _, rets, _ = load_market_series()

    print("=== ① 横截面短期反转 (t日 top3/bottom3 主题 -> t+1 收益) ===")
    top_r, bot_r = [], []
    for t in range(len(r) - 1):
        mask = ~np.isnan(r[t])
        if mask.sum() < 6:
            continue
        cols = np.where(mask)[0]
        order = np.argsort(r[t][mask])
        top, bot = cols[order[-3:]], cols[order[:3]]
        top_r.append(np.nanmean(r[t + 1][top]))
        bot_r.append(np.nanmean(r[t + 1][bot]))
    top_r, bot_r = np.array(top_r), np.array(bot_r)
    spread = bot_r - top_r
    ts = spread.mean() / (spread.std() / np.sqrt(len(spread))) if spread.std() > 0 else 0
    print(f"  top3(当日最强) 次日均收益 {top_r.mean():+.5f}")
    print(f"  bot3(当日最弱) 次日均收益 {bot_r.mean():+.5f}")
    print(f"  bot-top = {spread.mean():+.5f}  t={ts:+.2f}  "
          f"({'反转*' if ts > 2 else '动量' if ts < -2 else '无显著'})")

    print("\n=== ② 时序极端日次日收益 (市场综合) ===")
    z = (rets - rets.mean()) / rets.std()
    for thr, label in [(1.5, "暴涨 z>+1.5"), (-1.5, "暴跌 z<-1.5")]:
        idx = np.where(z > thr)[0] if thr > 0 else np.where(z < thr)[0]
        fwd = [rets[i + 1] for i in idx if i + 1 < len(rets)]
        mean = np.mean(fwd) if fwd else float("nan")
        print(f"  {label}: n={len(fwd)}  次日均收益 {mean:+.4f}")


def section2_stocks() -> None:
    with open(os.path.join(DATA, "stocks", "close_series.json"), encoding="utf-8") as f:
        d = json.load(f)
    stocks = d["stocks"]
    codes = list(stocks.keys())
    n_days = len(d["dates"])

    print(f"\n=== ③ 个股层 ARCH + 横截面动量 (全算 {len(codes)} 只, {n_days} 日) ===")
    # 收益矩阵 (个股×日), 用于横截面 rho
    m = np.full((len(codes), n_days - 1), np.nan)
    arch_cnt = 0
    valid = 0
    for i, c in enumerate(codes):
        p = np.array(stocks[c], dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            lr = np.diff(np.log(p))
        m[i, :len(lr)] = lr
        lr = lr[np.isfinite(lr)]
        if len(lr) < 60:
            continue
        valid += 1
        _, p_arch = ljung_box(lr ** 2, NLAGS)
        if p_arch < 0.05:
            arch_cnt += 1
    print(f"  个股 ARCH (r² LB<0.05): {arch_cnt}/{valid} = {arch_cnt / valid * 100:.0f}%")
    print("  对比: 主题ETF 4/30 = 13% (联合 p≈0.06 不显著)")
    expected_fp = 0.05 * valid
    print(f"  期望假阳性 ~{expected_fp:.0f} -> {'ARCH 在个股普遍存在' if arch_cnt > expected_fp * 3 else '证据仍弱'}")

    # 全市场横截面 rho (列=日期)
    rhos = []
    for t in range(m.shape[1] - 1):
        x, y = m[:, t], m[:, t + 1]
        mask = ~(np.isnan(x) | np.isnan(y))
        if mask.sum() >= 50:
            rho, _ = spearmanr(x[mask], y[mask])
            rhos.append(rho)
    rhos = np.array(rhos)
    ts = rhos.mean() / (rhos.std() / np.sqrt(len(rhos))) if rhos.std() > 0 else 0
    print(f"\n  全市场横截面 ρ (个股当日排名->次日): mean={rhos.mean():+.4f}  t={ts:+.2f}  n={len(rhos)}")
    print("  对比: 主题 ρ=-0.009 (≈0); 个股若 ρ<0 显著 = 经典短期反转")


if __name__ == "__main__":
    section1_event()
    section2_stocks()
