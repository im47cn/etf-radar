"""信号证据统计工具: ACF/PACF/Ljung-Box/IC/ARCH/GARCH 纯计算.

从 scripts/research/ 抽出的生产级实现, mypy strict. 纯函数无 IO.
IC = 横截面 spearman(strength[t], forward_return[t]); ARCH = r² 的 Ljung-Box.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize  # type: ignore[import-untyped]
from scipy.stats import chi2, percentileofscore, spearmanr  # type: ignore[import-untyped]


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


def hurst_exponent(
    x: NDArray[np.float64], min_samples: int = 100,
) -> float | None:
    """R/S (重标极差) Hurst 指数: log-log 回归 E[R/S] vs 块大小 k 的斜率.

    H<0.5 均值回归 (网格友好), H=0.5 随机游走, H>0.5 趋势延续 (网格危险).
    有效样本 <min_samples 返回 None (子区间不足, H 估计不稳). 钳制到 [0,1].
    """
    valid = x[np.isfinite(x)]
    n = len(valid)
    if n < min_samples:
        return None
    log_k: list[float] = []
    log_rs: list[float] = []
    for k in range(4, n // 2 + 1):
        n_blocks = n // k
        if n_blocks < 2:
            continue
        rs_vals: list[float] = []
        for b in range(n_blocks):
            block = valid[b * k:(b + 1) * k]
            dev = block - block.mean()
            cumdev = np.cumsum(dev)
            r = float(cumdev.max() - cumdev.min())
            s = float(block.std(ddof=1))
            if s > 0:
                rs_vals.append(r / s)
        if rs_vals:
            log_k.append(float(np.log(k)))
            log_rs.append(float(np.log(np.mean(rs_vals))))
    if len(log_k) < 3:
        return None
    coeffs = np.polyfit(np.array(log_k), np.array(log_rs), 1)
    h = float(coeffs[0])
    return min(1.0, max(0.0, h))


def annualized_volatility(
    x: NDArray[np.float64], periods: int = 252,
) -> float | None:
    """年化波动率 = std(valid, ddof=1) × sqrt(periods). <2 有效值返回 None."""
    valid = x[np.isfinite(x)]
    if len(valid) < 2:
        return None
    return float(np.std(valid, ddof=1) * np.sqrt(periods))


def percentile_rank(values: list[float], target: float) -> float:
    """target 在 values 中的百分位 [0,1] (percentileofscore mean 法, 处理 ties)."""
    if not values:
        return 0.0
    return float(percentileofscore(values, target, kind="mean") / 100.0)


# ---- GARCH(1,1) 前瞻波动率 ----
# 可行性已验证 (scripts/research/garch_grid_feasibility.py, 预注册):
# 60日前瞻 QLIKE 显著优于无条件基线 (p=0.0038); EWMA 不显著, 不可替代。
_GARCH_MIN_SAMPLES = 100


def fit_garch11(r: NDArray[np.float64]) -> tuple[float, float, float, float] | None:
    """零均值正态 GARCH(1,1) MLE。返回 (ω, α, β, σ²_T); 拟合失败返回 None。"""
    valid = r[np.isfinite(r)]
    n = len(valid)
    if n < _GARCH_MIN_SAMPLES:
        return None
    r2 = valid ** 2
    var0 = float(r2.mean())

    def nll(theta: NDArray[np.float64]) -> float:
        om, al, be = (float(theta[0]), float(theta[1]), float(theta[2]))
        if om <= 0 or al < 0 or be < 0 or al + be >= 0.999:
            return 1e12
        s2 = var0
        ll = -0.5 * (np.log(2 * np.pi) + np.log(s2) + r2[0] / s2)
        for t in range(1, n):
            s2 = om + al * r2[t - 1] + be * s2
            if s2 <= 0:
                return 1e12
            ll += -0.5 * (np.log(2 * np.pi) + np.log(s2) + r2[t] / s2)
        return -float(ll)

    # 初值: 常见 GARCH 校准 (α=0.1, β=0.85, ω=var·(1−α−β))
    res = minimize(nll, np.array([var0 * 0.05, 0.10, 0.85]), method="L-BFGS-B",
                   bounds=[(1e-12, None), (0.0, 0.999), (0.0, 0.999)])
    if not res.success or float(res.fun) >= 1e11:
        return None
    om, al, be = (float(res.x[0]), float(res.x[1]), float(res.x[2]))
    # 用收敛参数重算 σ²_T
    s2 = var0
    for t in range(1, n):
        s2 = om + al * r2[t - 1] + be * s2
    return om, al, be, s2


def garch_forecast_sigma(params: tuple[float, float, float, float], horizon: int) -> float:
    """未来 1..horizon 日 σ² 路径平均的 sqrt (σ²_{T+k}=ω+(α+β)σ²_{T+k-1})."""
    om, al, be, s2 = params
    total, s = 0.0, s2
    for _ in range(horizon):
        s = om + (al + be) * s
        total += s
    return float(np.sqrt(total / horizon))


def forecast_vol_annualized(
    r: NDArray[np.float64], horizon: int = 60, periods: int = 252,
) -> float | None:
    """GARCH(1,1) 前瞻 horizon 日平均日波动 × sqrt(periods) → 年化波动率。"""
    params = fit_garch11(r)
    if params is None:
        return None
    return float(garch_forecast_sigma(params, horizon) * np.sqrt(periods))
