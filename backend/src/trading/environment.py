"""市场环境档位 + defense 硬 gating + 宽度佐证 — SEPA 口径 (spec 2026-08-20 §1.1).

三指数跑 8 条趋势模板 (指数无 RS, 第 7 条恒 False, 最多 7/8):
- >=2 只 pass>=6 -> offense; >=2 只 pass<=3 -> defense; 否则 neutral
- defense 硬 gating: 下游 in_buy_zone/near_buy_zone 全部冻结为 watch
- 宽度佐证只展示不进档位公式 (读 data/latest/market_temperature.json, 缺失降级 null)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ..providers.base import ProviderError
from .trend import TrendResult, compute_trend

log = logging.getLogger(__name__)

Array = NDArray[np.float64]

INDEX_CODES: dict[str, str] = {'000300': '沪深300', '000905': '中证500', '399006': '创业板指'}
RS_BENCHMARK = '000985'  # 中证全指, RS 相对基准
OFFENSE_MIN, DEFENSE_MAX = 6, 3  # pass>=6 计进攻票, pass<=3 计防守票
MIN_ALIVE_INDICES = 2  # 可用指数 <2 时环境档位无法判定 -> 核心失败

Regime = str  # 'offense' | 'neutral' | 'defense'


def classify_regime(pass_counts: list[int]) -> Regime:
    """档位规则: >=2 只 >=6 -> offense; >=2 只 <=3 -> defense; 否则 neutral。"""
    if sum(1 for p in pass_counts if p >= OFFENSE_MIN) >= 2:
        return 'offense'
    if sum(1 for p in pass_counts if p <= DEFENSE_MAX) >= 2:
        return 'defense'
    return 'neutral'


def index_entry(code: str, name: str, closes: Array, trend: TrendResult) -> dict[str, Any]:
    """组装 §2.3 environment.indices 单条。"""
    return {
        'code': code,
        'name': name,
        'template_pass': trend.pass_count,
        'criteria': trend.criteria,
        'close': round(float(closes[-1]), 4),
    }


def compute_environment(index_closes: dict[str, Array]) -> dict[str, Any]:
    """各指数跑模板 -> 档位。可用指数 <2 抛 ProviderError (核心失败, CI 可见)。

    单只指数数据过短 (compute_trend None) 视为该指数不可用。
    """
    alive: list[dict[str, Any]] = []
    for code, name in INDEX_CODES.items():
        closes = index_closes.get(code)
        if closes is None:
            continue
        trend = compute_trend(closes, closes, closes, rs_pct=None)  # 指数只有收盘价, 三序列同源
        if trend is None:
            log.warning('trading env index %s data too short, dropped', code)
            continue
        alive.append(index_entry(code, name, closes, trend))
    if len(alive) < MIN_ALIVE_INDICES:
        raise ProviderError(
            f'trading: environment needs >= {MIN_ALIVE_INDICES} indices, got {len(alive)}'
        )
    return {
        'regime': classify_regime([e['template_pass'] for e in alive]),
        'indices': alive,
    }


def apply_defense_gating(candidates: list[dict[str, Any]], regime: Regime) -> list[dict[str, Any]]:
    """defense 档冻结: in_buy_zone/near_buy_zone -> watch (浅拷贝, 不改入参)。"""
    if regime != 'defense':
        return candidates
    out: list[dict[str, Any]] = []
    for cand in candidates:
        c = dict(cand)
        if c.get('state') in ('in_buy_zone', 'near_buy_zone'):
            c['state'] = 'watch'
        out.append(c)
    return out


def read_breadth(data_root: Path) -> dict[str, Any] | None:
    """读 market_temperature.json 的 ma20/60/120 市场宽度尾值; 缺失/损坏返回 None。"""
    path = Path(data_root) / 'latest' / 'market_temperature.json'
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
        periods = doc['periods']
        out: dict[str, Any] = {'source': 'market_temperature.json'}
        for key in ('ma20', 'ma60', 'ma120'):
            market = periods[key]['market']  # [{date, rate(0-100)}, ...]
            if not market:
                return None
            out[f'{key}_pct'] = round(float(market[-1]['rate']) / 100.0, 4)
        return out
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        log.warning('trading breadth degraded: %s', e)
        return None
