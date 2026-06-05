"""单只 ETF 的多周期对数收益率计算"""
import math

import pandas as pd  # type: ignore[import-untyped]

from ..models import Returns


def _log_return(series: pd.Series, periods: int) -> float | None:
    if len(series) <= periods:
        return None
    end = float(series.iloc[-1])
    start = float(series.iloc[-1 - periods])
    if start <= 0 or end <= 0:
        return None
    return math.log(end / start)


def _ytd_return(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    last = df.iloc[-1]
    last_year = int(last['date'].year)
    same_year = df[df['date'].dt.year == last_year]
    if len(same_year) < 2:
        return None
    first_close = float(same_year.iloc[0]['close'])
    end_close = float(last['close'])
    if first_close <= 0 or end_close <= 0:
        return None
    return math.log(end_close / first_close)


def compute_returns(df: pd.DataFrame) -> Returns:
    """df 已按 date 升序, 含 close 列。返回 6 个周期的对数收益率, 数据不足时返回 None。"""
    close: pd.Series = df['close']
    return Returns(
        r_1d=_log_return(close, 1),
        r_5d=_log_return(close, 5),
        r_20d=_log_return(close, 20),
        r_60d=_log_return(close, 60),
        r_120d=_log_return(close, 120),
        r_ytd=_ytd_return(df),
    )
