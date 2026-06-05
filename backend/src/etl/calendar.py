"""交易日历 — A 股 + 美股"""
from datetime import date, datetime, time, timezone, timedelta
import chinese_calendar  # type: ignore[import-untyped]
import pandas_market_calendars as mcal  # type: ignore[import-untyped]

BJT = timezone(timedelta(hours=8))
NYSE = mcal.get_calendar('NYSE')

CN_MORNING_OPEN = time(9, 30)
CN_MORNING_CLOSE = time(11, 30)
CN_AFTERNOON_OPEN = time(13, 0)
CN_AFTERNOON_CLOSE = time(15, 0)


def is_cn_trading_day(d: date) -> bool:
    try:
        return chinese_calendar.is_workday(d) and not chinese_calendar.is_holiday(d)
    except NotImplementedError:
        # chinese_calendar 暂无该年份数据, 保守返回 False
        return False


def is_us_trading_day(d: date) -> bool:
    schedule = NYSE.schedule(start_date=d, end_date=d)
    return not schedule.empty


def is_cn_session_active(now_bjt: datetime) -> bool:
    if not is_cn_trading_day(now_bjt.date()):
        return False
    t = now_bjt.time()
    return (CN_MORNING_OPEN <= t <= CN_MORNING_CLOSE
            or CN_AFTERNOON_OPEN <= t <= CN_AFTERNOON_CLOSE)


def is_us_session_active(now_utc: datetime) -> bool:
    """美股盘中: ET 09:30-16:00 (UTC-5/-4)"""
    d = now_utc.astimezone(timezone.utc).date()
    sched = NYSE.schedule(start_date=d, end_date=d)
    if sched.empty:
        return False
    market_open = sched.iloc[0]['market_open'].to_pydatetime()
    market_close = sched.iloc[0]['market_close'].to_pydatetime()
    return bool(market_open <= now_utc <= market_close)
