"""自建个股宽度计算: SMA/站上/有效样本过滤/多周期聚合."""
from __future__ import annotations


from src.market_breadth.self_breadth import compute_self_breadth


def _cs(dates, stocks):
    return {'dates': dates, 'stocks': stocks}


def test_sma_and_above_basic():
    # 3 天, MA2: day1 起可算. 股A: [10,12,11] -> MA2 day1=11(12>11 above), day2=11.5(11<11.5 below)
    cs = _cs(['d0', 'd1', 'd2'], {'A': [10.0, 12.0, 11.0]})
    snap = compute_self_breadth(cs, {}, periods=(2,))
    mkt = {m['date']: m['rate'] for m in snap['periods']['ma2']['market']}
    assert mkt['d0'] is None          # 历史不足 MA2
    assert mkt['d1'] == 100.0         # 12 > MA2(11)
    assert mkt['d2'] == 0.0           # 11 < MA2(11.5)


def test_new_stock_insufficient_history_excluded():
    # 股B 只有 2 个有效值 < MA3, 全程不计入分母
    cs = _cs(['d0', 'd1', 'd2'], {'A': [10.0, 11.0, 12.0], 'B': [None, 5.0, 6.0]})
    snap = compute_self_breadth(cs, {}, periods=(3,))
    m = {x['date']: x['rate'] for x in snap['periods']['ma3']['market']}
    # 只有 A 在 d2 有 MA3: mean(10,11,12)=11, 12>11 above -> 100%; B 被排除
    assert m['d2'] == 100.0
    assert m['d0'] is None and m['d1'] is None


def test_halt_null_excluded_from_denominator():
    # 股A d2 停牌(null): d2 该股无效; MA2 用最近两个有效收盘
    cs = _cs(['d0', 'd1', 'd2', 'd3'], {'A': [10.0, 12.0, None, 20.0]})
    snap = compute_self_breadth(cs, {}, periods=(2,))
    m = {x['date']: x['rate'] for x in snap['periods']['ma2']['market']}
    assert m['d2'] is None            # 停牌日无有效样本
    # d3: 最近两个有效收盘 [12,20], MA2=16, 20>16 above
    assert m['d3'] == 100.0


def test_industry_l1_l2_aggregation():
    cs = _cs(['d0', 'd1'], {
        'A': [10.0, 20.0],  # MA1... 用 period=1: 每日 close>SMA1(=close) 恒 False. 用 period=1 不合适
    })
    # 用 period=2 与两股, 同 L1 不同 L2
    cs = _cs(['d0', 'd1', 'd2'], {
        'A': [10.0, 12.0, 15.0],   # d1: 12>11 above; d2: 15>13.5 above
        'B': [10.0, 12.0, 10.0],   # d1: 12>11 above; d2: 10<11 below
    })
    imap = {'A': {'l1': '电子', 'l2': '半导体'}, 'B': {'l1': '电子', 'l2': '消费电子'}}
    snap = compute_self_breadth(cs, imap, periods=(2,))
    l1 = {r['name']: r for r in snap['periods']['ma2']['industries_l1']}
    l2 = {r['name']: r for r in snap['periods']['ma2']['industries_l2']}
    # d2: 电子(A,B) = 1/2 above = 50%
    assert l1['电子']['series'][2] == 50.0
    assert l2['半导体']['series'][2] == 100.0
    assert l2['消费电子']['series'][2] == 0.0


def test_unmapped_stock_in_market_not_industry():
    cs = _cs(['d0', 'd1'], {'A': [10.0, 20.0], 'B': [10.0, 5.0]})
    imap = {'A': {'l1': '电子', 'l2': '半导体'}}  # B 无归属
    snap = compute_self_breadth(cs, imap, periods=(2,))
    # 全市场 d1: A(20>15 above)+B(5<7.5 below)=1/2=50%
    assert snap['periods']['ma2']['market'][1]['rate'] == 50.0
    # 行业只含 A
    l2 = {r['name']: r for r in snap['periods']['ma2']['industries_l2']}
    assert '半导体' in l2 and l2['半导体']['series'][1] == 100.0


def test_multi_period_and_shape():
    cs = _cs([f'd{i}' for i in range(5)], {'A': [10.0, 11.0, 12.0, 13.0, 14.0]})
    snap = compute_self_breadth(cs, {}, periods=(2, 3))
    assert snap['schema_version'] == '2.0'
    assert set(snap['periods'].keys()) == {'ma2', 'ma3'}
    for pk in ('ma2', 'ma3'):
        assert len(snap['periods'][pk]['market']) == 5


def test_ma120_insufficient_history_all_null():
    cs = _cs([f'd{i}' for i in range(10)], {'A': [float(i) for i in range(10)]})
    snap = compute_self_breadth(cs, {}, periods=(120,))
    rates = [m['rate'] for m in snap['periods']['ma120']['market']]
    assert all(r is None for r in rates)
