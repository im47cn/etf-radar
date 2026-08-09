"""时间序列研究共享工具: ACF/PACF/Ljung-Box + 数据加载.

供 research/ 下各分析脚本复用, 消除重复定义. 纯 numpy + scipy.
数据根: backend/scripts/research/ -> 上溯 3 级到仓库根的 data/snapshots.
"""
from __future__ import annotations

import json
import os

import numpy as np
from scipy.stats import chi2  # type: ignore[import-untyped]

SNAP = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "snapshots")


def _dates() -> list[str]:
    return sorted(d for d in os.listdir(SNAP) if len(d) == 10 and d[4] == "-")


def load_themes(date: str) -> list[dict]:
    """读某日 snapshot 的 themes 列表 (context-managed)."""
    with open(os.path.join(SNAP, date, "themes.json"), encoding="utf-8") as f:
        return json.load(f)["themes"]


def acf(x: np.ndarray, nlags: int) -> np.ndarray:
    """自相关函数 (lag 0..nlags)."""
    x = x - x.mean()
    v = np.dot(x, x) / len(x)
    if v == 0:
        return np.zeros(nlags + 1)
    n = len(x)
    return np.array([np.dot(x[: n - k], x[k:]) / (n * v) for k in range(nlags + 1)])


def pacf(x: np.ndarray, nlags: int) -> np.ndarray:
    """偏自相关 (Durbin-Levinson 递归)."""
    r = acf(x, nlags)
    phi = np.zeros((nlags + 1, nlags + 1))
    res = np.zeros(nlags + 1)
    sigma = r[0]
    for k in range(1, nlags + 1):
        if sigma <= 0:
            res[k] = 0.0
            continue
        acc = r[k] - sum(phi[k - 1][j] * r[k - j] for j in range(1, k))
        pk = acc / sigma
        phi[k][k] = pk
        for j in range(1, k):
            phi[k][j] = phi[k - 1][j] - pk * phi[k - 1][k - j]
        res[k] = pk
        sigma *= 1 - pk * pk
    return res


def ljung_box(x: np.ndarray, m: int) -> tuple[float, float]:
    """Ljung-Box Q + p-value (H0: 前 m 阶 ACF 全为 0)."""
    n = len(x)
    r = acf(x, m)
    q = n * (n + 2) * sum(r[k] ** 2 / (n - k) for k in range(1, m + 1))
    return float(q), float(1.0 - chi2.cdf(q, m))


def load_market_series() -> tuple[list[str], np.ndarray, np.ndarray]:
    """(dates, 市场综合r_1d=横截面均值, 横截面std=分化度)."""
    dates = _dates()
    rets, cs_std = [], []
    for d in dates:
        rs = [t.get("returns", {}).get("r_1d") for t in load_themes(d)]
        rs = [r for r in rs if r is not None]
        rets.append(float(np.mean(rs)))
        cs_std.append(float(np.std(rs)))
    return dates, np.array(rets), np.array(cs_std)


def load_matrix() -> tuple[list[str], list[str], np.ndarray]:
    """日×主题 r_1d 矩阵 (缺失填 nan)."""
    dates = _dates()
    names = [t["id"] for t in load_themes(dates[0])]
    m = np.full((len(dates), len(names)), np.nan)
    for i, d in enumerate(dates):
        for j, t in enumerate(load_themes(d)):
            r = t.get("returns", {}).get("r_1d")
            if r is not None:
                m[i, j] = float(r)
    return dates, names, m
