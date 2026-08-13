"""信号证据统计工具: ACF/PACF/Ljung-Box/IC/ARCH 纯计算.

从 scripts/research/ 抽出的生产级实现, mypy strict. 纯函数无 IO.
IC = 横截面 spearman(strength[t], forward_return[t]); ARCH = r² 的 Ljung-Box.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.stats import chi2, spearmanr  # type: ignore[import-untyped]


def acf(x: NDArray[np.float64], nlags: int) -> NDArray[np.float64]:
    """自相关函数 (lag 0..nlags)."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    v = np.dot(x, x) / len(x)
    if v == 0:
        return np.zeros(nlags + 1)
    n = len(x)
    return np.array([np.dot(x[: n - k], x[k:]) / (n * v) for k in range(nlags + 1)])


def pacf(x: NDArray[np.float64], nlags: int) -> NDArray[np.float64]:
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


def ljung_box(x: NDArray[np.float64], m: int) -> tuple[float, float]:
    """Ljung-Box Q + p-value (H0: 前 m 阶 ACF 全为 0)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    r = acf(x, m)
    q = n * (n + 2) * sum(r[k] ** 2 / (n - k) for k in range(1, m + 1))
    # 用 survival function 算右尾 p, 避免 1 - cdf 在大 q 下下溢为 0.0
    # (强 ARCH 主题 q 可达数百, 1-cdf 会因浮点精度归零, 使最显著的反而渲染成 0 高度)
    return float(q), float(chi2.sf(q, m))


def forward_cum(r: NDArray[np.float64], k: int) -> NDArray[np.float64]:
    """t 期未来 k 日累计 log return = sum(r[t+1..t+k]). 无前视, 末端 nan.

    r 形状 (T,) 或 (T, N); 沿时间轴 (axis 0) 累加, 缺失用 nansum 跳过.
    """
    r = np.asarray(r, dtype=float)
    n = r.shape[0]
    f = np.full_like(r, np.nan)
    for t in range(n - k):
        f[t] = np.nansum(r[t + 1:t + 1 + k], axis=0)
    return f


def _daily_ic(strength_col: NDArray[np.float64], fwd_col: NDArray[np.float64]) -> float | None:
    """单日横截面 spearman IC; 有效主题对 <5 或 rho=nan 时返回 None."""
    mask = ~(np.isnan(strength_col) | np.isnan(fwd_col))
    if int(mask.sum()) < 5:
        return None
    res = spearmanr(strength_col[mask], fwd_col[mask])
    rho = float(res.correlation)
    return None if np.isnan(rho) else rho


def ic_by_horizon(
    strength: NDArray[np.float64], returns: NDArray[np.float64],
    horizons: tuple[int, ...] = (1, 5, 20),
    recent_n: int = 5,
) -> list[dict[str, object]]:
    """逐 horizon 全样本横截面 IC: 均值/t_stat/n + ic_min/ic_max (全样本范围) + recent_ic (近 recent_n 日均值)."""
    out: list[dict[str, object]] = []
    for h in horizons:
        fwd = forward_cum(returns, h)
        ics = [v for v in (_daily_ic(strength[t], fwd[t])
                           for t in range(len(strength) - h)) if v is not None]
        arr = np.array(ics, dtype=float)
        if len(arr) < 2:
            out.append({"horizon": h, "ic": 0.0, "t_stat": 0.0, "n": len(arr),
                        "ic_min": None, "ic_max": None, "recent_ic": None})
            continue
        mean = float(arr.mean())
        std = float(arr.std())
        # std=0 (如完美相关, IC 恒定) 时 mean 仍有效, 仅 t_stat 不可估计
        t_stat = 0.0 if std == 0 else float(mean / (std / np.sqrt(len(arr))))
        recent = arr[-recent_n:] if len(arr) >= recent_n else arr
        out.append({
            "horizon": h, "ic": mean, "t_stat": t_stat, "n": len(arr),
            "ic_min": float(arr.min()), "ic_max": float(arr.max()),
            "recent_ic": float(recent.mean()),
        })
    return out


def rolling_ic_multi(
    strength: NDArray[np.float64], returns: NDArray[np.float64], dates: list[str],
    windows: tuple[int, ...] = (5, 20, 60), horizon: int = 20,
) -> list[dict[str, object]]:
    """多窗口滚动 IC 时序: 对每日 t 算以 t 为终点的各窗口逐日横截面 IC 均值.

    返回 [{date, ic_<w>...}], 窗口内有效 IC 不足 w//2 时该档 None; 防前视 t+horizon<=T.
    t 从 max(windows)-1 起 (三档同起点便于对比).
    """
    n = len(strength)
    fwd = forward_cum(returns, horizon)
    daily: list[float | None] = [
        None if t >= n - horizon else _daily_ic(strength[t], fwd[t]) for t in range(n)
    ]
    max_w = max(windows)
    out: list[dict[str, object]] = []
    for t in range(max_w - 1, n - horizon):
        row: dict[str, object] = {"date": dates[t]}
        for w in windows:
            seg = [v for v in daily[t - w + 1:t + 1] if v is not None]
            row[f"ic_{w}"] = float(np.mean(seg)) if len(seg) >= w // 2 else None
        out.append(row)
    return out


def arch_per_theme(
    returns: NDArray[np.float64], names: list[str], m: int = 10,
    min_samples: int = 40,
) -> list[dict[str, object]]:
    """每主题 ARCH 检验: r² 的 Ljung-Box (McLeod-Li) + 收益白噪检验.

    返回 [{theme_id, n, r2_lb_p, is_arch, ret_lb_p}], 有效样本 <min_samples 跳过.
    min_samples 默认 40; 最新未完整季可降到 m+1 (技术下限, 保证 n>m 能算 Ljung-Box).
    """
    out: list[dict[str, object]] = []
    for j in range(returns.shape[1]):
        col = returns[:, j]
        valid = col[np.isfinite(col)]
        if len(valid) < min_samples:
            continue
        _, p_arch = ljung_box(valid ** 2, m)
        _, p_ret = ljung_box(valid, m)
        out.append({
            "theme_id": names[j], "n": len(valid),
            "r2_lb_p": p_arch, "is_arch": bool(p_arch < 0.05), "ret_lb_p": p_ret,
        })
    return out
