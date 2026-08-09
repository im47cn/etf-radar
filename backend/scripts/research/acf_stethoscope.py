#!/usr/bin/env python
"""ACF/PACF 听诊器: 扫描 snapshots/ 的陈旧/重复/插值回声.

三层诊断 (按信号强度排序):
  1. 全字段冻结指纹 —— theme 的所有数值分量与前一快照逐字节相同.
     单分量偶然相等正常 (百分位天然离散), 但 8+ 分量同时相同 = 强陈旧指纹,
     规避了"离散序列相邻相等属正常"的混淆.
  2. ACF(1) —— 异常高 (>1.96/sqrt(n) 且接近 1) 提示隐蔽的部分重复/插值.
  3. PACF —— 检测周期性回退 (如某 provider 每周固定日回退 -> lag≈5 凸起).

ACF/PACF 复用 ts_utils. 读 data/snapshots/<date>/themes.json.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from ts_utils import acf, load_themes, pacf

SNAP = Path(__file__).resolve().parents[3] / "data" / "snapshots"
STRENGTH_FIELDS = ("cn_strength", "us_strength")
NLAGS = 10


def _dates() -> list[str]:
    return sorted(d for d in os.listdir(SNAP) if (SNAP / d).is_dir())


def _theme_fingerprint(theme: dict) -> tuple:
    """theme 所有强度数值叶子的稳定指纹 (cn+us 的 short/mid/long/composite)."""
    leaves: list[float] = []
    for fld in STRENGTH_FIELDS:
        v = theme.get(fld)
        if isinstance(v, dict):
            for k in ("short", "mid", "long", "composite"):
                if isinstance(v.get(k), (int, float)):
                    leaves.append(float(v[k]))
    return tuple(leaves)


def _composite(theme: dict, side: str) -> float | None:
    v = theme.get(f"{side}_strength")
    if isinstance(v, dict) and isinstance(v.get("composite"), (int, float)):
        return float(v["composite"])
    return None


def main() -> None:
    dates = _dates()
    n = len(dates)
    if n < 5:
        print(f"快照不足 ({n}), 无法诊断"); return

    # 一次性加载: 指纹 (冻结用) + cn composite (ACF/PACF 用)
    fps: list[list[tuple]] = []
    cn_comp: list[list[float | None]] = []
    names: list[str] | None = None
    for d in dates:
        try:
            themes = load_themes(d)
        except Exception as e:  # noqa: BLE001
            print(f"跳过 {d}: {e}"); fps.append([]); cn_comp.append([]); continue
        names = [t.get("id", str(i)) for i, t in enumerate(themes)]
        fps.append([_theme_fingerprint(t) for t in themes])
        cn_comp.append([_composite(t, "cn") for t in themes])
    nt = len(names or [])

    band = 1.96 / np.sqrt(n)
    print("=== ACF 听诊器 ===")
    print(f"快照 {n} 个 ({dates[0]} ~ {dates[-1]}), {nt} 主题, 95% 带 = ±{band:.3f}\n")

    # 1. 全字段冻结 (主信号)
    print("[1] 全字段冻结快照对 (theme 8 分量与前日逐字节相同):")
    freeze_by_date: dict[str, int] = {}
    for di in range(1, n):
        if not fps[di] or not fps[di - 1]:
            continue
        cnt = sum(1 for ti in range(nt)
                  if ti < len(fps[di]) and ti < len(fps[di - 1])
                  and fps[di][ti] and fps[di][ti] == fps[di - 1][ti])
        if cnt:
            freeze_by_date[dates[di]] = cnt
    if freeze_by_date:
        tot = sum(freeze_by_date.values())
        worst = sorted(freeze_by_date.items(), key=lambda kv: -kv[1])[:10]
        for d, c in worst:
            flag = "  <-- 高度可疑" if c >= nt * 0.5 else ""
            print(f"  {d}: {c}/{nt} 主题冻结{flag}")
        print(f"  合计冻结事件 {tot} (主题×日), 占比 {tot/(nt*(n-1))*100:.1f}%")
    else:
        print("  无")
    print()

    # 2/3. 逐主题 ACF(1) + PACF 周期性
    print("[2] 逐主题 cn_strength.composite 诊断:")
    print(f"  {'theme':<14}{'acf1':>8}{'rep%':>7}{'pacf峰值lag':>14}")
    suspects: list[tuple] = []
    for ti in range(nt):
        vals = [cn_comp[di][ti] for di in range(n) if ti < len(cn_comp[di])]
        arr = np.array([v for v in vals if v is not None], float)
        if len(arr) < 10 or arr.std() == 0:
            continue
        a = acf(arr, NLAGS)
        p = pacf(arr, NLAGS)
        rep = np.mean(arr[1:] == arr[:-1]) * 100
        peak_lag = int(np.argmax(np.abs(p[1:])) + 1)
        flag = ""
        if a[1] > band and rep > 40:
            flag = "  <-- 疑似重复/陈旧"
            suspects.append((names[ti], a[1], rep, peak_lag))
        print(f"  {str(names[ti])[:14]:<14}{a[1]:>8.3f}{rep:>6.1f}%{peak_lag:>14}{flag}")

    print("\n[3] 结论:")
    if freeze_by_date:
        print(f"  - 发现 {len(freeze_by_date)} 个快照存在全字段冻结, 强烈建议人工核对这些日期")
        print("    的数据源回退日志 (em RemoteDisconnected -> sina 回退取旧 bar 的典型签名).")
    if suspects:
        print(f"  - {len(suspects)} 个主题 ACF(1) 显著且重复率>40%, 可能有部分重复/插值.")
    if not freeze_by_date and not suspects:
        print("  - 未检出明显陈旧/重复签名.")


if __name__ == "__main__":
    main()
