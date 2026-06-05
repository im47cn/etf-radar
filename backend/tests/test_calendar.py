from datetime import date, datetime, timezone, timedelta
from src.etl.calendar import (
    is_cn_trading_day, is_us_trading_day,
    is_cn_session_active,
)


def test_cn_weekend_is_not_trading() -> None:
    sat = date(2026, 6, 6)  # Saturday
    assert not is_cn_trading_day(sat)


def test_us_weekend_is_not_trading() -> None:
    sun = date(2026, 6, 7)  # Sunday
    assert not is_us_trading_day(sun)


def test_cn_normal_workday_is_trading() -> None:
    mon = date(2026, 6, 8)  # Monday (not holiday)
    assert is_cn_trading_day(mon)


def test_cn_session_active_during_morning() -> None:
    BJT = timezone(timedelta(hours=8))
    dt = datetime(2026, 6, 8, 10, 0, tzinfo=BJT)
    assert is_cn_session_active(dt)


def test_cn_session_inactive_during_lunch() -> None:
    BJT = timezone(timedelta(hours=8))
    dt = datetime(2026, 6, 8, 12, 0, tzinfo=BJT)
    assert not is_cn_session_active(dt)


def test_cn_session_inactive_before_open() -> None:
    BJT = timezone(timedelta(hours=8))
    dt = datetime(2026, 6, 8, 9, 0, tzinfo=BJT)
    assert not is_cn_session_active(dt)
