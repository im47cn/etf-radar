#!/usr/bin/env python
"""单主题 ARCH 检验: 验证市场综合的 r² 白噪是否为"分散化抹平"假象.

方法: McLeod-Li 检验 (对 r_1d² 做 Ljung-Box), 等价 ARCH-LM 大样本版.
若多数主题 r² 非白噪 (p<0.05) 而市场综合白噪 -> ARCH 真实存在, 组合分散化抹平了它.
多重检验警告: 30 主题期望假阳性 ~1.5 个, arch_count 须明显超过才可信.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from ts_utils import SNAP, acf, ljung_box, load_themes

NLAGS = 15


def load_per_theme() -> tuple[list[str], dict[str, list[float]]]:
    dates = sorted(d for d in os.listdir(SNAP) if len(d) == 10 and d[4] == "-")
    th0 = load_themes(dates[0])
    names = [t["id"] for t in th0]
    series: dict[str, list[float]] = {n: [] for n in names}
    for d in dates:
        th = load_themes(d)
        for t in th:
            r = t.get("returns", {}).get("r_1d")
            if r is not None:
                series[t["id"]].append(float(r))
    return names, series


def main() -> None:
    names, series = load_per_theme()
    print(f"单主题 ARCH 检验 (McLeod-Li = r² 的 Ljung-Box, m={NLAGS})\n")
    print(f"{'主题':<16}{'n':>5}{'收益LB_p':>10}{'r²LB_p':>10}{'r²ACF1':>9}  判定")
    print("-" * 62)

    arch, tested, ret_predict = 0, 0, 0
    rows = []
    for name in names:
        x = np.array(series[name])
        if len(x) < 60:
            print(f"{name:<16}{len(x):>5}  样本不足, 跳过")
            continue
        tested += 1
        _, p_ret = ljung_box(x, NLAGS)
        _, p_arch = ljung_box(x ** 2, NLAGS)
        a2_1 = acf(x ** 2, 1)[1]
        is_arch = p_arch < 0.05
        if is_arch:
            arch += 1
        if p_ret < 0.05:
            ret_predict += 1
        rows.append((name, len(x), p_ret, p_arch, a2_1, is_arch, p_ret < 0.05))

    # 按 ARCH 显著性排序, 显著的在前
    rows.sort(key=lambda r: (not r[5], r[3]))
    for name, n, p_ret, p_arch, a2_1, is_arch, is_ret in rows:
        flag = "ARCH*" if is_arch else ""
        ret_flag = " 收益可预测" if is_ret else ""
        print(f"{name:<16}{n:>5}{p_ret:>10.3f}{p_arch:>10.3f}{a2_1:>9.3f}  {flag}{ret_flag}")

    print("-" * 62)
    expected_fp = 0.05 * tested
    print(f"\n汇总: {arch}/{tested} 主题存在 ARCH (r² p<0.05)")
    print(f"      {ret_predict}/{tested} 主题收益可预测 (r_1d p<0.05)")
    print(f"      多重检验期望假阳性 ~{expected_fp:.1f} 个 -> "
          f"{'ARCH 真实存在' if arch > expected_fp * 2 else 'ARCH 证据不足'}")
    print("\n对照: 市场综合(30主题均值) r² LB_p=0.667 = 白噪")
    print("      -> 若上面 ARCH 比例高, 坐实'组合分散化抹平了个股波动率聚集'")


if __name__ == "__main__":
    main()
