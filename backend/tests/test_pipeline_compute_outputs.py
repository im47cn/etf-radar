"""compute_outputs() as-of 行为单测"""
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd  # type: ignore[import-untyped]
import pytest

from src.config_loader import load_algo_config, load_themes
from src.models import ThemeConfig
from src.pipeline import PipelineMode, compute_outputs

BJT = ZoneInfo('Asia/Shanghai')


def _make_ohlc(start: str, n: int, base: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.date_range(start, periods=n, tz='UTC'),
        'open': [base] * n,
        'high': [base * 1.01] * n,
        'low': [base * 0.99] * n,
        'close': [base + i * step for i in range(n)],
        'volume': [10000] * n,
        'amount': [base * 10000.0] * n,
    })


@pytest.fixture
def config():
    config_dir = Path(__file__).parent.parent.parent / 'config'
    themes = load_themes(config_dir / 'themes.yml')
    algo = load_algo_config(config_dir / 'algo.yml')
    return themes, algo


def test_compute_outputs_asof_reflects_in_generated_at(config):
    """asof_bjt 应作为 generated_at 时间戳源"""
    themes, algo = config
    us_ohlc = {sym: _make_ohlc('2025-01-01', 200) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-01-01', 200) for t in themes for cn in t.cn_etfs}
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    themes_json, _, _, _ = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    assert themes_json['generated_at'].startswith('2026-04-15T16:00')


def test_compute_outputs_calendar_reflects_asof_date(config):
    """calendar.cn_trading_today 应基于 asof_bjt 日期判定"""
    themes, algo = config
    us_ohlc = {sym: _make_ohlc('2025-01-01', 200) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-01-01', 200) for t in themes for cn in t.cn_etfs}
    # 2026-06-06 是周六, 必定非交易日, 不依赖任何节假日数据库
    asof = datetime(2026, 6, 6, 16, 0, tzinfo=BJT)

    _, _, _, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    assert meta_json['calendar']['cn_trading_today'] is False


def test_compute_outputs_returns_reflect_asof_truncation(config):
    """切片到 D 日的 close, r_1d 应等于 ln(close[D]/close[D-1])"""
    themes, algo = config
    # 200 天数据, 我们切到第 100 天 D
    us_ohlc = {sym: _make_ohlc('2025-01-01', 200) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-01-01', 200) for t in themes for cn in t.cn_etfs}

    # 切片到第 100 天 (index 99)
    D_idx = 99
    sliced_us = {k: v.iloc[:D_idx + 1].copy() for k, v in us_ohlc.items()}
    sliced_cn = {k: v.iloc[:D_idx + 1].copy() for k, v in cn_ohlc.items()}
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    themes_json, _, _, _ = compute_outputs(
        themes, sliced_us, sliced_cn, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    # base=100, step=0.5, r_1d = ln(close[99]/close[98]) = ln(149.5/149.0)
    expected_r1d = math.log(149.5 / 149.0)
    actual = themes_json['themes'][0]['returns']['r_1d']
    assert abs(actual - expected_r1d) < 1e-6


def test_compute_outputs_ytd_crosses_year_boundary(config):
    """asof 2026-01-15 时, r_ytd 应基于 2026 起点, 不应回退到 2025"""
    themes, algo = config
    # 数据从 2025-10-01 到 2026-01-20, 包含跨年
    n = (datetime(2026, 1, 20) - datetime(2025, 10, 1)).days + 1
    us_ohlc = {sym: _make_ohlc('2025-10-01', n) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-10-01', n) for t in themes for cn in t.cn_etfs}

    # 切到 2026-01-15 (index = (2026-01-15 - 2025-10-01).days)
    D_idx = (datetime(2026, 1, 15) - datetime(2025, 10, 1)).days
    sliced_us = {k: v.iloc[:D_idx + 1].copy() for k, v in us_ohlc.items()}
    sliced_cn = {k: v.iloc[:D_idx + 1].copy() for k, v in cn_ohlc.items()}
    asof = datetime(2026, 1, 15, 16, 0, tzinfo=BJT)

    themes_json, _, _, _ = compute_outputs(
        themes, sliced_us, sliced_cn, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    actual = themes_json['themes'][0]['returns']['r_ytd']
    assert actual is not None
    # 收紧断言: 用 _ytd_return 的实际行为（same_year.iloc[0]['close']）手算期望值
    sym0_df = sliced_us[next(iter(sliced_us))]
    first_2026 = sym0_df[sym0_df['date'].dt.year == 2026].iloc[0]
    expected_ytd = math.log(sym0_df['close'].iloc[-1] / first_2026['close'])
    assert abs(actual - expected_ytd) < 1e-6


def test_compute_outputs_backfilled_flag_propagates(config):
    themes, algo = config
    us_ohlc = {sym: _make_ohlc('2025-01-01', 200) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-01-01', 200) for t in themes for cn in t.cn_etfs}
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    _, _, _, meta_default = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )
    _, _, _, meta_backfilled = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
        backfilled=True,
    )

    assert meta_default['backfilled'] is False
    assert meta_backfilled['backfilled'] is True


def test_compute_outputs_handles_empty_cache(config):
    """全部 symbol 数据为空 — 不应崩溃, returns 全 None, strength 全 0"""
    themes, algo = config
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    themes_json, etfs_json, signals_json, meta_json = compute_outputs(
        themes, {}, {},
        list({sym for t in themes for sym in t.us_etfs}),
        list({cn.code for t in themes for cn in t.cn_etfs}),
        algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    assert themes_json['themes'][0]['returns']['r_1d'] is None
    assert themes_json['themes'][0]['strength']['composite'] == 0
    assert meta_json['providers']['us']['status'] == 'degraded'
    assert meta_json['providers']['cn']['status'] == 'degraded'


def test_compute_outputs_cn_fallback_status(config):
    """cn_failed=[], cn_fallback_map 非空时，cn provider status 应为 'fallback'"""
    themes, algo = config
    us_ohlc = {sym: _make_ohlc('2025-01-01', 200) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-01-01', 200) for t in themes for cn in t.cn_etfs}
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    _, _, _, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
        cn_fallback_map={'159755': 'akshare-sina'},
    )

    assert meta_json['providers']['cn']['status'] == 'fallback'
    assert meta_json['fallback_symbols'] == {'159755': 'akshare-sina'}
    assert meta_json['providers']['cn']['name'] == 'akshare-em'


# ── Task 4 新增测试 ────────────────────────────────────────────────────────────

import numpy as np
from src.models import CnEtfConfig


def _fake_ohlc(n: int = 200, base: float = 100.0, drift: float = 0.001) -> pd.DataFrame:
    """生成带随机游走的合成 OHLC，用于 cn_only 主题测试。"""
    rng = np.random.default_rng(42)
    closes = base * np.cumprod(1 + rng.normal(drift, 0.01, n))
    dates = pd.date_range('2025-01-01', periods=n, freq='B', tz='UTC')
    return pd.DataFrame(
        {'open': closes, 'high': closes * 1.001, 'low': closes * 0.999,
         'close': closes, 'volume': 1.0, 'amount': 1e8},
        index=dates,
    ).reset_index().rename(columns={'index': 'date'})


def test_compute_outputs_cn_only_theme_no_us_strength():
    """纯 A 股主题：us_strength 应为 None，cn_strength 非空，strength == cn_strength。"""
    config_dir = Path(__file__).parent.parent.parent / 'config'
    algo = load_algo_config(config_dir / 'algo.yml')

    themes = [
        ThemeConfig(
            id='mapped', name='M',
            us_etfs=['SOXX'], primary_us='SOXX', tags=[],
            cn_etfs=[CnEtfConfig(code='000001', name='X', tracking='T', match_type='exact')],
        ),
        ThemeConfig(
            id='cn_x', name='X',
            primary_cn='000002', tags=[],
            cn_etfs=[CnEtfConfig(code='000002', name='Y', tracking='T2', match_type='exact')],
        ),
    ]
    us_ohlc = {'SOXX': _fake_ohlc(base=100)}
    cn_ohlc = {'000001': _fake_ohlc(base=10), '000002': _fake_ohlc(base=20)}
    asof = datetime(2025, 6, 19, 16, 0, tzinfo=BJT)

    themes_json, etfs_json, signals_json, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo,
        asof_bjt=asof, mode=PipelineMode.ARCHIVE,
    )

    by_id = {t['id']: t for t in themes_json['themes']}
    mapped = by_id['mapped']
    cn_only = by_id['cn_x']

    # mapped 主题双端都有
    assert mapped['us_strength'] is not None
    assert mapped['cn_strength'] is not None

    # cn_only 主题：us 无，cn 有，整体 strength == cn_strength
    assert cn_only['us_strength'] is None
    assert cn_only['cn_strength'] is not None
    assert cn_only['strength'] == cn_only['cn_strength']


def test_compute_outputs_schema_version_bumped():
    """themes_json.schema_version 应升至 '1.1'，meta_json 应含 theme_kinds。"""
    config_dir = Path(__file__).parent.parent.parent / 'config'
    algo = load_algo_config(config_dir / 'algo.yml')

    themes = [
        ThemeConfig(
            id='m', name='M',
            us_etfs=['SOXX'], primary_us='SOXX', tags=[],
            cn_etfs=[CnEtfConfig(code='000001', name='X', tracking='T', match_type='exact')],
        ),
        ThemeConfig(
            id='cn_y', name='Y',
            primary_cn='000002', tags=[],
            cn_etfs=[CnEtfConfig(code='000002', name='Z', tracking='T2', match_type='exact')],
        ),
    ]
    us_ohlc = {'SOXX': _fake_ohlc()}
    cn_ohlc = {'000001': _fake_ohlc(), '000002': _fake_ohlc(base=50)}
    asof = datetime(2025, 6, 19, 16, 0, tzinfo=BJT)

    themes_json, _, _, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo,
        asof_bjt=asof, mode=PipelineMode.ARCHIVE,
    )

    assert themes_json['schema_version'] == '1.1'
    assert meta_json['theme_kinds'] == {'mapped': 1, 'cn_only': 1}
