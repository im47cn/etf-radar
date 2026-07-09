"""dapanyuntu 全市场 MA20 对账."""
from __future__ import annotations

from src.market_breadth.reconcile import reconcile


def _self(rate):
    return {'periods': {'ma20': {'market': [{'date': '2026-07-01', 'rate': rate}]}}}


def _dpyt(rate):
    return {'market': [{'date': '2026-07-02', 'rate': rate}]}


def test_within_threshold():
    qc = reconcile(_self(32.9), _dpyt(30.4), threshold=5.0)
    assert qc['abs_diff'] == 2.5
    assert qc['over_threshold'] is False
    assert qc['self']['rate'] == 32.9 and qc['dapanyuntu']['rate'] == 30.4


def test_over_threshold():
    qc = reconcile(_self(50.0), _dpyt(30.0), threshold=5.0)
    assert qc['abs_diff'] == 20.0 and qc['over_threshold'] is True


def test_latest_non_null_picked():
    s = {'periods': {'ma20': {'market': [{'date': 'd0', 'rate': 40.0}, {'date': 'd1', 'rate': None}]}}}
    qc = reconcile(s, _dpyt(38.0))
    assert qc['self'] == {'date': 'd0', 'rate': 40.0}


def test_missing_data_no_diff():
    qc = reconcile({'periods': {'ma20': {'market': []}}}, _dpyt(30.0))
    assert qc['self'] is None and qc['abs_diff'] is None and qc['over_threshold'] is False


# --- self_stale (C3) ---

def test_self_stale_when_self_date_before_dpyt():
    # _self 固定 2026-07-01, _dpyt 固定 2026-07-02 → self as-of 落后
    qc = reconcile(_self(32.0), _dpyt(30.0))
    assert qc['self_stale'] is True


def test_self_stale_false_when_dates_equal():
    s = {'periods': {'ma20': {'market': [{'date': '2026-07-02', 'rate': 32.0}]}}}
    qc = reconcile(s, _dpyt(30.0))
    assert qc['self_stale'] is False


def test_self_stale_false_when_dpyt_missing():
    qc = reconcile(_self(32.0), {'market': []})
    assert qc['self_stale'] is False


def test_self_stale_false_when_self_missing():
    qc = reconcile({'periods': {'ma20': {'market': []}}}, _dpyt(30.0))
    assert qc['self_stale'] is False
