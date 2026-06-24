"""双轨强度评分: 百分位 × sigmoid 动量"""
import math
from statistics import mean

from scipy.stats import percentileofscore  # type: ignore[import-untyped]

from ..models import DimName, Returns

DIM_FIELDS: dict[str, list[str]] = {
    'short': ['r_1d', 'r_5d'],
    'mid': ['r_20d', 'r_60d'],
    'long': ['r_120d', 'r_ytd'],
}


def sigmoid_momentum(ret: float, k: float, days_in_dim: int) -> float:
    """对数收益率年化后过 sigmoid 映射到 0-100"""
    annualized = ret * (252 / days_in_dim)
    return 100.0 / (1.0 + math.exp(-k * annualized))


def percentile_rank(value: float, pool: list[float]) -> float:
    """value 在 pool 内的百分位排名 (0-100)"""
    return float(percentileofscore(pool, value, kind='rank'))


def dim_aggregate_return(returns: Returns, dim: DimName) -> float | None:
    """单维度内子周期平均"""
    fields = DIM_FIELDS[dim]
    values = [getattr(returns, f) for f in fields]
    non_null = [v for v in values if v is not None]
    if not non_null:
        return None
    return float(mean(non_null))


def strength_per_dim(
    own_dim_return: float,
    pool_dim_returns: list[float],
    k: float,
    days_in_dim: int,
) -> int:
    """单维度双轨强度: 0.5×百分位 + 0.5×sigmoid, 返回 0-99 整数

    上限 99 是硬约束 (min(99, ...)), 100 不会出现; 设计意图是给出
    "几乎完美但不绝对"的语义边界, 避免 UI 上 100 显得过于绝对。

    Raises:
        ValueError: 当 pool_dim_returns 为空 (percentileofscore 返回 NaN, round 会崩溃)
    """
    if not pool_dim_returns:
        raise ValueError("pool_dim_returns must not be empty")
    P = percentile_rank(own_dim_return, pool_dim_returns)
    M = sigmoid_momentum(own_dim_return, k=k, days_in_dim=days_in_dim)
    raw = 0.5 * P + 0.5 * M
    return max(0, min(99, round(raw)))


def composite_strength(
    short: int,
    mid: int,
    long: int,
    w_short: float,
    w_mid: float,
    w_long: float,
) -> int:
    assert abs(w_short + w_mid + w_long - 1.0) < 1e-9, \
        f"weights must sum to 1.0, got {w_short + w_mid + w_long}"
    return round(w_short * short + w_mid * mid + w_long * long)


def batch_strength_per_dim(
    returns_array: 'np.ndarray',
    k: float,
    days_in_dim: int,
) -> 'np.ndarray':
    """向量化版本：N 只股一次性算百分位 + 动量。

    避免 N² 复杂度（原 strength_per_dim 每只股都遍历 pool）。
    输入 NaN 自动传播；返回数组中无效位置保持 NaN。

    Args:
        returns_array: N 只股票的收益率数组（可含 NaN）
        k: sigmoid 陡峭系数
        days_in_dim: 维度天数（用于年化计算）

    Returns:
        长度 N 的 float ndarray，有效值在 [0, 99]，无效为 NaN。
    """
    import numpy as np
    from scipy.stats import rankdata  # type: ignore[import-untyped]

    n = len(returns_array)
    if n == 0:
        return np.array([], dtype=float)

    valid_mask = ~np.isnan(returns_array)
    n_valid = int(valid_mask.sum())

    P = np.full(n, np.nan)
    if n_valid > 0:
        ranks = rankdata(returns_array[valid_mask], method='average')
        P[valid_mask] = (ranks / n_valid) * 100

    annualized = returns_array * (252 / days_in_dim)
    M = 100.0 / (1.0 + np.exp(-k * annualized))

    raw = 0.5 * P + 0.5 * M
    score = np.clip(np.round(raw), 0, 99)
    score[np.isnan(raw)] = np.nan
    return score
