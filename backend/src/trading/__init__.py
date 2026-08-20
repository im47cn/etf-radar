"""SEPA 交易信号管线 (spec 2026-08-20): 趋势模板/VCP/环境档位/筛选漏斗 -> trading.json。"""
from .environment import apply_defense_gating, classify_regime, compute_environment, read_breadth
from .pipeline import run
from .screen import StockBars, compute_rs_percentiles, screen_universe
from .trend import TrendResult, compute_trend, sma
from .vcp import VcpResult, classify_state, find_vcp, zigzag

__all__ = [
    'StockBars',
    'TrendResult',
    'VcpResult',
    'apply_defense_gating',
    'classify_regime',
    'classify_state',
    'compute_environment',
    'compute_rs_percentiles',
    'compute_trend',
    'find_vcp',
    'read_breadth',
    'run',
    'screen_universe',
    'sma',
    'zigzag',
]
