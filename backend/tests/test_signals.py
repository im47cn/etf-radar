from pathlib import Path

import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from src.config_loader import load_algo_config
from src.models import Strength, ThemeConfig, CnEtfConfig
from src.pipeline import compute_outputs, PipelineMode
from src.scoring.signals import (
    judge_per_period,
    signal_for_pair,
    signal_for_theme,
)

BJT = timezone(timedelta(hours=8))


def _fake_ohlc(n=200, base=100.0):
    rng = np.random.default_rng(7)
    closes = base * np.cumprod(1 + rng.normal(0.001, 0.01, n))
    return pd.DataFrame({
        'date': pd.date_range('2025-01-01', periods=n, freq='B', tz='UTC'),
        'open': closes, 'high': closes * 1.01, 'low': closes * 0.99,
        'close': closes, 'volume': 1.0, 'amount': 1e8,
    })

CFG = load_algo_config(Path(__file__).parent / 'fixtures' / 'algo_minimal.yml')


def test_resonance_when_both_strong_and_same_dir() -> None:
    sig = judge_per_period(us_str=80, cn_str=75, us_ret=0.05, cn_ret=0.04, cfg=CFG.signal)
    assert sig == 'resonance'


def test_transmission_when_us_leads() -> None:
    sig = judge_per_period(us_str=80, cn_str=40, us_ret=0.05, cn_ret=0.0, cfg=CFG.signal)
    assert sig == 'transmission'


def test_transmission_reverse_cn_leads() -> None:
    """反向传导: A 股领先美股 (罕见但保留)"""
    sig = judge_per_period(us_str=40, cn_str=80, us_ret=0.0, cn_ret=0.05, cfg=CFG.signal)
    assert sig == 'transmission'


def test_divergence_when_opposite_dir() -> None:
    sig = judge_per_period(us_str=60, cn_str=60, us_ret=0.05, cn_ret=-0.05, cfg=CFG.signal)
    assert sig == 'divergence'


def test_neutral_when_weak() -> None:
    """双方都弱 + 收益太小 → 无信号"""
    sig = judge_per_period(us_str=40, cn_str=40, us_ret=0.001, cn_ret=0.001, cfg=CFG.signal)
    assert sig is None


def test_signal_for_pair_votes_resonance() -> None:
    """三周期全 resonance → resonance"""
    sig, votes = signal_for_pair(
        us_strength=Strength(short=80, mid=80, long=80, composite=80),
        cn_strength=Strength(short=75, mid=75, long=75, composite=75),
        us_dim_returns={'short': 0.05, 'mid': 0.10, 'long': 0.30},
        cn_dim_returns={'short': 0.04, 'mid': 0.09, 'long': 0.28},
        cfg=CFG.signal,
    )
    assert sig == 'resonance'
    assert all(v == 'resonance' for v in votes.values())


def test_signal_for_pair_no_majority_returns_none() -> None:
    """1 resonance + 2 None → 无多数, 返回 None"""
    sig, _votes = signal_for_pair(
        us_strength=Strength(short=80, mid=40, long=40, composite=53),
        cn_strength=Strength(short=75, mid=40, long=40, composite=52),
        us_dim_returns={'short': 0.05, 'mid': 0.001, 'long': 0.001},
        cn_dim_returns={'short': 0.04, 'mid': 0.001, 'long': 0.001},
        cfg=CFG.signal,
    )
    assert sig is None


def test_signal_for_theme_picks_highest_confidence() -> None:
    """按 (confidence, mapping_score) 降序, 取第一个有信号的候选"""
    us_str = Strength(short=80, mid=80, long=80, composite=80)
    us_ret = {'short': 0.05, 'mid': 0.10, 'long': 0.30}
    candidates = [
        # 低置信度: 共振信号
        {
            'code': '000001',
            'confidence': 60,
            'mapping_score': 80,
            'cn_strength': Strength(short=75, mid=75, long=75, composite=75),
            'cn_dim_returns': {'short': 0.04, 'mid': 0.09, 'long': 0.28},
        },
        # 高置信度: 也是共振信号 (强度接近 + 同向 + 都强)
        {
            'code': '000002',
            'confidence': 90,
            'mapping_score': 70,
            'cn_strength': Strength(short=72, mid=72, long=72, composite=72),
            'cn_dim_returns': {'short': 0.045, 'mid': 0.09, 'long': 0.28},
        },
    ]
    sig, code, _votes = signal_for_theme(
        us_strength=us_str, us_dim_returns=us_ret,
        cn_candidates=candidates, cfg=CFG.signal,
    )
    # 应按 confidence 90 > 60 选 000002
    assert sig == 'resonance'
    assert code == '000002'


def test_signal_for_theme_skips_neutral_candidate() -> None:
    """高 confidence 候选无信号时, 落到下一个候选"""
    us_str = Strength(short=80, mid=80, long=80, composite=80)
    us_ret = {'short': 0.05, 'mid': 0.10, 'long': 0.30}
    candidates = [
        # 高置信度但无信号 (us 强 cn 中等且方向都+, 差值刚好不在共振/传导阈值内)
        # us-cn=80-50=30 >= 25 且 us>=65 → 实际会触发 transmission... 改成 cn 更接近 us 但不够强
        # 让 cn_str=50, us-cn=30 ≥ 25 + us=80 ≥ 65 → transmission. 不好。
        # 改成 cn_str=66 → diff=14 ≤ 15 (共振阈值), max(80,66)=80≥60 → 共振...
        # 用 dim_returns 全 0 来阻止信号
        {
            'code': '000002',
            'confidence': 90,
            'mapping_score': 70,
            'cn_strength': Strength(short=66, mid=66, long=66, composite=66),
            'cn_dim_returns': {'short': 0.0, 'mid': 0.0, 'long': 0.0},
        },
        # 低置信度: 有共振信号
        {
            'code': '000001',
            'confidence': 60,
            'mapping_score': 80,
            'cn_strength': Strength(short=75, mid=75, long=75, composite=75),
            'cn_dim_returns': {'short': 0.04, 'mid': 0.09, 'long': 0.28},
        },
    ]
    sig, code, _votes = signal_for_theme(
        us_strength=us_str, us_dim_returns=us_ret,
        cn_candidates=candidates, cfg=CFG.signal,
    )
    # 000002 cn_ret 全 0 (_sign 为 0) → judge_per_period 共振要求 _sign(us_ret)!=0 同时 _sign(cn_ret)!=0 → 失败
    # 传导 us_str=80, cn_str=66, diff=14 < 25 → 不触发传导
    # 背离 _sign 不同要求双方都非零 → 失败 → None
    # 跳到 000001 → 共振
    assert sig == 'resonance'
    assert code == '000001'


def test_signal_for_theme_no_candidates_returns_none() -> None:
    sig, code, votes = signal_for_theme(
        us_strength=Strength(short=80, mid=80, long=80, composite=80),
        us_dim_returns={'short': 0.05, 'mid': 0.10, 'long': 0.30},
        cn_candidates=[],
        cfg=CFG.signal,
    )
    assert sig is None
    assert code is None
    assert votes == {}


def test_cn_only_theme_has_null_signal():
    themes = [
        ThemeConfig(id='cn_x', name='X', primary_cn='000001', tags=[],
                    cn_etfs=[CnEtfConfig(code='000001', name='Y', tracking='T', match_type='exact')]),
    ]
    cn_ohlc = {'000001': _fake_ohlc(base=10)}
    algo = load_algo_config(Path(__file__).parent.parent.parent / 'config' / 'algo.yml')
    asof = datetime(2025, 6, 19, 16, 0, tzinfo=BJT)
    _, _, signals_json, _ = compute_outputs(
        themes, {}, cn_ohlc, [], [], algo, asof, PipelineMode.ARCHIVE,
    )

    ts = [s for s in signals_json['theme_signals'] if s['theme_id'] == 'cn_x'][0]
    assert ts['signal'] is None
    assert ts['trigger_cn_etf'] is None or ts['trigger_cn_etf'] == '000001'
    summary = signals_json['summary']
    assert summary['resonance_count'] == 0
    assert summary['transmission_count'] == 0
    assert summary['divergence_count'] == 0
