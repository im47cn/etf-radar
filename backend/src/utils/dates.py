from datetime import date, timedelta


def next_weekday(d: date) -> date:
    """返回严格下一个工作日（周一~周五）的日期。"""
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:  # 5=周六, 6=周日
        nxt += timedelta(days=1)
    return nxt


def prev_weekday(d: date) -> date:
    """返回严格前一个工作日（周一~周五）的日期。"""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # 5=周六, 6=周日
        prev -= timedelta(days=1)
    return prev


def is_weekend(d: date) -> bool:
    """判断给定日期是否为周末（周六或周日）。"""
    return d.weekday() >= 5  # 5=周六, 6=周日
