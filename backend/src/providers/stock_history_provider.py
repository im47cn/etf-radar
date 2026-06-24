"""个股历史 K 线 Provider（封装 ak.stock_zh_a_hist）"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import akshare as ak
import pandas as pd

from ..models import StockOhlcBar

log = logging.getLogger(__name__)


class StockHistoryFetchError(Exception):
    """历史 K 线抓取失败（含重试耗尽与空返回）"""


@dataclass
class StockHistoryProvider:
    """封装 akshare 历史接口 + 指数退避重试。

    akshare 对 symbol 前缀自动判断（'sh' / 'sz' / 'bj'），
    本 Provider 不做手工前缀，直接传 6 位 code。
    """
    max_retries: int = 3
    base_backoff: float = 0.5

    def fetch_history(self, code: str, days: int) -> list[StockOhlcBar]:
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                df: pd.DataFrame = ak.stock_zh_a_hist(
                    symbol=code,
                    period='daily',
                    adjust='qfq',
                )
                if df is None or df.empty:
                    raise StockHistoryFetchError(f'{code}: empty dataframe')
                return self._df_to_bars(df, days)
            except StockHistoryFetchError:
                raise
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    backoff = self.base_backoff * (2 ** attempt)
                    log.warning(f'{code} retry {attempt + 1} after {backoff}s: {e}')
                    time.sleep(backoff)
        raise StockHistoryFetchError(f'{code} fetch failed: {last_err}')

    @staticmethod
    def _df_to_bars(df: pd.DataFrame, days: int) -> list[StockOhlcBar]:
        df = df.tail(days).reset_index(drop=True)
        bars: list[StockOhlcBar] = []
        for _, row in df.iterrows():
            dt = row['日期']
            d = dt.date() if hasattr(dt, 'date') else dt
            bars.append(StockOhlcBar(
                date=d,
                o=float(row['开盘']),
                h=float(row['最高']),
                l=float(row['最低']),
                c=float(row['收盘']),
                v=int(row['成交量']),
            ))
        return bars
