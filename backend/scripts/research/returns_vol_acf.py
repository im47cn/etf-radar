#!/usr/bin/env python
"""收益率/波动率 ACF/PACF 回测: 验证经典金融事实 + 信号可预测性基础.

经典事实 (stylized facts):
  1. 收益率 ACF ≈ 0 (白噪)        -> 市场近似有效, 收益不可预测
  2. 收益率² ACF 显著拖尾          -> 波动率聚集 (ARCH 效应)
  3. 波动率 ACF 缓慢衰减 (长记忆)  -> 高波动后倾向延续高波动

标的: 市场综合收益 = 30 主题 r_1d 横截面均值.
波动率双定义: 时序 (20日滚动std) + 横截面 (当日30主题r_1d的std = 分化度).
Ljung-Box 联合检验补充逐 lag ACF 的解读.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from ts_utils import acf, ljung_box, load_market_series, pacf

NLAGS = 15


def report(name: str, x: np.ndarray) -> None:
    x = np.asarray(x, float)
    band = 1.96 / np.sqrt(len(x))
    a, p = acf(x, NLAGS), pacf(x, NLAGS)
    print(f"\n=== {name}  (n={len(x)}, 95%带=±{band:.3f}) ===")
    print(f"{'lag':>4}{'ACF':>9}{'PACF':>9}")
    for k in range(1, NLAGS + 1):
        mark = " *" if abs(a[k]) > band else ""
        print(f"{k:>4}{a[k]:>9.3f}{p[k]:>9.3f}{mark}")
    q, pv = ljung_box(x, NLAGS)
    verdict = "显著(非白噪)" if pv < 0.05 else "白噪"
    print(f"Ljung-Box(m={NLAGS}): Q={q:.2f}  p={pv:.4f}  -> {verdict}")


def main() -> None:
    dates, rets, cs_std = load_market_series()
    print(f"交易日: {len(dates)} 个 ({dates[0]} ~ {dates[-1]})")
    print(f"市场综合 r_1d: 均值={rets.mean():.5f}, std={rets.std():.5f}, "
          f"min={rets.min():.4f}, max={rets.max():.4f}")

    # 1. 收益率 (应白噪)
    report("① 收益率 r_1d (市场综合)", rets)

    # 2. 收益率² (波动率聚集代理; 应显著拖尾)
    report("② 收益率² r_1d² (波动率聚集代理)", rets ** 2)

    # 3. 时序波动率 (20日滚动std)
    roll = np.array([rets[max(0, i - 19):i + 1].std() for i in range(len(rets))])
    report("③ 时序波动率 (r_1d 的20日滚动std)", roll[20:])

    # 4. 横截面波动率 (当日分化度)
    report("④ 横截面波动率 (当日30主题r_1d的std)", cs_std)


if __name__ == "__main__":
    main()
