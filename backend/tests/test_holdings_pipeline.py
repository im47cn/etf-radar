"""holdings_pipeline 主流程及辅助函数测试"""
from datetime import date

from src.holdings_pipeline import candidate_quarters


def test_candidate_quarters_january():
    # Jan 15 2026 → 最近季末是 2025-12-31，候选回退到 2025-12/09/06/03
    out = candidate_quarters(date(2026, 1, 15))
    assert out == [date(2025, 12, 31), date(2025, 9, 30), date(2025, 6, 30), date(2025, 3, 31)]


def test_candidate_quarters_on_quarter_end():
    # 3 月 31 日当天 → 当季已结束，候选首位是 2026-03-31
    out = candidate_quarters(date(2026, 3, 31))
    assert out[0] == date(2026, 3, 31)
    assert out[1] == date(2025, 12, 31)


def test_candidate_quarters_mid_quarter():
    # 5 月 1 日 → 最近季末是 2026-03-31
    out = candidate_quarters(date(2026, 5, 1))
    assert out[0] == date(2026, 3, 31)


def test_candidate_quarters_returns_four():
    out = candidate_quarters(date(2026, 7, 15))
    assert len(out) == 4
