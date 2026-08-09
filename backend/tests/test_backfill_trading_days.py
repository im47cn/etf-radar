"""backfill _iter_trading_days 门控测试: 确保只生成 CN 交易日, 不再污染 snapshots."""
from datetime import date

from scripts.backfill_snapshots import _iter_trading_days
from src.etl.calendar import is_cn_trading_day


def test_only_cn_trading_days_returned():
    """跨春节区间 (含周末+节假日+交易日) 的结果必须全部是 CN 交易日."""
    days = _iter_trading_days(date(2026, 2, 13), date(2026, 2, 27))
    # oracle: 每个返回日都应通过 is_cn_trading_day
    assert all(is_cn_trading_day(d) for d in days), days


def test_cn_holidays_excluded():
    """春节核心休市日 (CN 非交易日) 不应出现在结果中."""
    days = set(_iter_trading_days(date(2026, 2, 13), date(2026, 2, 27)))
    for holiday in (date(2026, 2, 17), date(2026, 2, 18),
                    date(2026, 2, 19), date(2026, 2, 20)):
        assert holiday not in days, f"{holiday} 不应被 backfill"


def test_weekends_excluded():
    """普通周末不应出现 (chinese_calendar 调休误判不影响, is_cn_trading_day 有 isoweekday 保护)."""
    days = set(_iter_trading_days(date(2026, 1, 2), date(2026, 1, 9)))
    for weekend in (date(2026, 1, 3), date(2026, 1, 4),  # 周六/日
                    date(2026, 1, 10)):                  # 下周六 (边界外应不含)
        assert weekend not in days


def test_us_only_day_excluded():
    """CN 休市但 US 开市的日子不应出现 (旧 CN OR US 逻辑会含, 纯 CN 判据不含)."""
    # 2026-02-17 春节首日: CN 休市, US 照常开市
    assert _iter_trading_days(date(2026, 2, 17), date(2026, 2, 17)) == []


def test_real_trading_days_preserved():
    """真实 CN 交易日应保留, 且结果有序."""
    days = _iter_trading_days(date(2026, 2, 13), date(2026, 2, 27))
    assert days == sorted(days)
    assert date(2026, 2, 13) in days  # 周五, 春节前最后交易日
    assert date(2026, 2, 27) in days  # 周五, 春节后
