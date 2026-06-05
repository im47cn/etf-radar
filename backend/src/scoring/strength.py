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
    """单维度双轨强度: 0.5×百分位 + 0.5×sigmoid, 返回 0-99 整数 (上限 99 留 100 给完美样本)"""
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
    return round(w_short * short + w_mid * mid + w_long * long)
