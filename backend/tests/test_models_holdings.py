"""Pydantic 校验 holdings 相关模型"""
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.models import EtfHoldingsSnapshot, EtfTopHolding, StockSpot


def test_etf_top_holding_valid():
    h = EtfTopHolding(code='002129', name='TCL中环', weight=8.5)
    assert h.code == '002129'
    assert h.weight == 8.5


def test_etf_top_holding_weight_range():
    # 权重必须 0-100
    with pytest.raises(ValidationError):
        EtfTopHolding(code='002129', name='TCL中环', weight=150.0)
    with pytest.raises(ValidationError):
        EtfTopHolding(code='002129', name='TCL中环', weight=-1.0)


def test_etf_holdings_snapshot_valid():
    snap = EtfHoldingsSnapshot(
        etf_code='512480',
        etf_name='半导体ETF',
        disclosure_date=date(2026, 3, 31),
        fetched_at=datetime(2026, 6, 23, 3, 0, tzinfo=timezone.utc),
        top_holdings=[
            EtfTopHolding(code='002129', name='TCL中环', weight=8.5),
            EtfTopHolding(code='603501', name='韦尔股份', weight=7.2),
        ],
    )
    assert len(snap.top_holdings) == 2


def test_etf_holdings_snapshot_max_10_holdings():
    holdings = [EtfTopHolding(code=f'00{i:04d}', name=f's{i}', weight=1.0) for i in range(11)]
    with pytest.raises(ValidationError):
        EtfHoldingsSnapshot(
            etf_code='512480',
            etf_name='x',
            disclosure_date=date(2026, 3, 31),
            fetched_at=datetime.now(timezone.utc),
            top_holdings=holdings,
        )


def test_stock_spot_valid():
    s = StockSpot(name='TCL中环', close=12.5, r_1d=0.025)
    assert s.r_1d == 0.025


def test_stock_spot_r1d_optional():
    # 停牌时 r_1d 可为 None
    s = StockSpot(name='TCL中环', close=12.5, r_1d=None)
    assert s.r_1d is None
