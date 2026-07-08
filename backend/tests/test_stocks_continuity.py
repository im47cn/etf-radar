"""连续性检测 missing_trading_days 单测(C4 self-heal 基石)。"""
from datetime import date

from src.stocks_continuity import missing_trading_days


def test_gap_on_single_trading_day():
    # 07-07 为周二(工作日交易日),序列缺失 → 应报出
    assert missing_trading_days(['2026-07-06', '2026-07-08']) == [date(2026, 7, 7)]


def test_continuous_sequence_no_gap():
    assert missing_trading_days(['2026-07-06', '2026-07-07', '2026-07-08']) == []


def test_weekend_not_reported():
    # 周五(07-03)→ 周一(07-06),中间周末非交易日,不报
    assert missing_trading_days(['2026-07-03', '2026-07-06']) == []


def test_empty_and_single():
    assert missing_trading_days([]) == []
    assert missing_trading_days(['2026-07-08']) == []


def test_multiple_gaps_sorted():
    # 缺 07-02(周四) 与 07-07(周二)
    result = missing_trading_days(['2026-07-01', '2026-07-03', '2026-07-06', '2026-07-08'])
    assert result == [date(2026, 7, 2), date(2026, 7, 7)]


def test_unsorted_input_handled():
    assert missing_trading_days(['2026-07-08', '2026-07-06']) == [date(2026, 7, 7)]
