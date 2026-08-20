"""screen.py 单测: 筛选漏斗逐层 / RS 百分位 / 综合分权重 (spec §1.3/§1 综合分)."""
from __future__ import annotations

import numpy as np
import pytest

from src.trading.screen import (
    StockBars,
    board_of,
    composite_score,
    compute_rs_percentiles,
    is_st,
    r60,
    screen_universe,
)
from tests.test_trading_fixtures import candidate_closes, geo, volumes


def bars(closes: list[float], volume: np.ndarray | None = None, amount: float = 2e8) -> StockBars:
    c = np.array(closes, dtype=np.float64)
    v = volume if volume is not None else np.full(len(c), 1e6)
    return StockBars(
        code='', open_=c.copy(), high=c * 1.001, low=c * 0.999, close=c,
        volume=v, amount=np.full(len(c), amount),
    )


def candidate_bars(scale: float = 1.0, amount: float = 2e8) -> StockBars:
    cs = [c * scale for c in candidate_closes()]
    return bars(cs, volumes(len(cs)), amount)


def test_is_st() -> None:
    assert is_st('ST测试') is True
    assert is_st('*ST测试') is True
    assert is_st('测试退') is True
    assert is_st('退市整理') is True
    assert is_st('贵州测试') is False


def test_board_of() -> None:
    assert board_of('600519') == 'main'
    assert board_of('000001') == 'main'
    assert board_of('002460') == 'main'
    assert board_of('300750') == 'chinext'
    assert board_of('688981') == 'star'
    assert board_of('830799') is None  # 北交所不入漏斗
    assert board_of('430047') is None


def test_r60_window_and_guard() -> None:
    assert r60(np.array(geo(61, 10.0, 1.01))) == pytest.approx(1.01**60 - 1, rel=1e-9)
    assert r60(np.array(geo(60, 10.0))) is None  # 不足 61 根
    assert r60(np.array([0.0] * 60 + [10.0])) is None  # 基准价非法


def test_compute_rs_percentiles_cross_section() -> None:
    out = compute_rs_percentiles({'A': 0.10, 'B': 0.05, 'C': 0.00}, bench_r60=0.02)
    assert out == {'A': 100.0, 'B': 66.7, 'C': 33.3}


def test_compute_rs_percentiles_benchmark_missing() -> None:
    assert compute_rs_percentiles({'A': 0.1}, bench_r60=None) == {}
    assert compute_rs_percentiles({}, bench_r60=0.02) == {}


def test_composite_score_weights() -> None:
    # 全项: 0.3*1 + 0.4*0.8 + 0.2*0.8 = 0.86 -> 8.6
    assert composite_score(8, 0.8, 80.0, None) == 8.6  # vol 缺 -> RS 权重 0.3: +0.24
    # vol 可得 (适配分 0.75): 0.3+0.32+0.12+0.075 = 0.815 -> 8.2
    assert composite_score(8, 0.8, 60.0, 0.2) == 8.2
    # RS 基准缺失: (0.3+0.32)/0.7 = 0.8857 -> 8.9
    assert composite_score(8, 0.8, None, None) == 8.9
    # RS 缺失但 vol 可得: (0.3+0.32+0.075)/0.8 = 0.86875 -> 8.7
    assert composite_score(8, 0.8, None, 0.2) == 8.7
    # 模板 6/8 + 一般质量
    assert composite_score(6, 0.5, 55.0, None) == 5.9


def _universe() -> tuple[dict[str, StockBars], dict[str, str]]:
    down = geo(300, 50.0, 0.997)
    universe = {
        '600001': candidate_bars(),
        '600002': candidate_bars(),  # ST
        '600003': candidate_bars(scale=2.5 / 98.0),  # 末价 2.5 < 3
        '600004': candidate_bars(),  # 次新 (截断)
        '600005': candidate_bars(amount=5e7),  # 20 日均额 < 1 亿
        '830006': candidate_bars(),  # 北交所
        '600007': bars(down),  # 下跌: tradable 但非 Stage 2
        '600008': bars(geo(300, 10.0, 1.003)),  # 上涨无 VCP (量能不萎缩)
        '300009': candidate_bars(),  # 创业板候选
    }
    universe['600004'] = bars(candidate_closes()[:100], volumes(100))
    names = {'600001': '贵州测试', '600002': 'ST测试', '600003': '低价测试', '600004': '次新测试',
             '600005': '流动性测试', '830006': '北交所测试', '600007': '下跌测试', '600008': '无收缩测试',
             '300009': '创业测试'}
    return universe, names


def test_screen_funnel_layer_counts() -> None:
    universe, names = _universe()
    rs = {'600001': 90.0, '300009': 80.0, '600007': 10.0, '600008': 70.0}
    cands, stats = screen_universe(universe, names, rs, {})
    assert stats == {'total': 9, 'tradable': 4, 'stage2': 3, 'vcp': 2, 'top': 2}
    assert [c['code'] for c in cands] == ['600001', '300009']  # 综合分降序


def test_screen_candidate_fields_match_contract() -> None:
    """候选字段名/结构与 §2.3 契约一致 (前端 lane 对接点)。"""
    universe, names = _universe()
    cands, _ = screen_universe(universe, names, {'600001': 90.0}, {'600001': 0.3})
    top = cands[0]
    assert set(top.keys()) == {
        'code', 'name', 'composite_score', 'stage', 'template_pass', 'rs_pct', 'vcp',
        'pivot', 'buy_zone_low', 'buy_zone_high', 'stop', 'state', 'limit_up_unexecutable',
        'chg_pct', 'board', 'vol_forecast_ann',
    }
    assert top['code'] == '600001'
    assert top['stage'] == 2
    assert top['template_pass'] == 8
    assert top['rs_pct'] == 90.0
    assert top['vol_forecast_ann'] == 0.3
    assert top['board'] == 'main'
    assert top['state'] == 'near_buy_zone'
    assert top['limit_up_unexecutable'] is False
    assert set(top['vcp'].keys()) == {'contractions', 'depth_pct', 'quality', 'volume_dryup'}
    assert top['vcp']['contractions'] == 3
    assert top['vcp']['depth_pct'] == 25.0  # 0-1 -> 百分数口径
    assert top['pivot'] == 100.0
    assert top['buy_zone_high'] == 105.0


def test_screen_rs_null_when_missing() -> None:
    universe, names = _universe()
    cands, _ = screen_universe(universe, names, {}, {})  # 基准挂: RS 空
    top = cands[0]
    assert top['rs_pct'] is None
    assert top['composite_score'] == 6.3  # RS 挂 -> 模板第7条也不过 (pass 7), (0.3*7/8+0.4*0.4458)/0.7


def test_screen_top_truncated_at_50() -> None:
    universe = {f'60{i:04d}': candidate_bars() for i in range(100, 155)}
    names = {c: f'股{c}' for c in universe}
    rs = {c: 50.0 for c in universe}
    cands, stats = screen_universe(universe, names, rs, {})
    assert stats['vcp'] == 55
    assert stats['top'] == 50
    assert len(cands) == 50
    # 同分 tie -> code 升序稳定截断
    assert cands[0]['code'] == '600100'
    assert cands[-1]['code'] == '600149'


def test_screen_limit_up_in_buy_zone_flagged() -> None:
    """末端一字板恰入买区 -> limit_up_unexecutable=True (无法买入提示)。"""
    cs = candidate_closes()
    cs[-2] = 94.5  # 昨收
    cs[-1] = 104.0  # 一字 +10.05%, 恰入买区 [100, 105]
    c = np.array(cs, dtype=np.float64)
    one_word = StockBars(
        code='600100', open_=c.copy(), high=c.copy(), low=c.copy(),
        close=c, volume=volumes(len(cs)), amount=np.full(len(cs), 2e8),
    )
    cands, _ = screen_universe({'600100': one_word}, {'600100': '一字测试'}, {'600100': 90.0}, {})
    assert len(cands) == 1
    top = cands[0]
    assert top['state'] == 'in_buy_zone'
    assert top['limit_up_unexecutable'] is True


def test_screen_limit_up_false_when_not_in_zone() -> None:
    """一字板但价格超买区上沿 -> state watch, 不打标记。"""
    cs = candidate_closes()
    cs[-2] = 94.5
    cs[-1] = 110.0  # +16.4% 一字, 超 105
    c = np.array(cs, dtype=np.float64)
    one_word = StockBars(
        code='600100', open_=c.copy(), high=c.copy(), low=c.copy(),
        close=c, volume=volumes(len(cs)), amount=np.full(len(cs), 2e8),
    )
    cands, _ = screen_universe({'600100': one_word}, {'600100': '一字测试'}, {'600100': 90.0}, {})
    top = cands[0]
    assert top['state'] == 'watch'
    assert top['limit_up_unexecutable'] is False
