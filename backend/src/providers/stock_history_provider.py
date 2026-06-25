"""个股历史 K 线 Provider（基于 ak.stock_zh_a_daily，新浪源）

历史背景：原先使用 ak.stock_zh_a_hist（东方财富），但该源对外网/某些 IP
段会触发 RemoteDisconnected。新浪 daily 源稳定且与东财字段一致，差异仅为
前缀（sh/sz/bj）。本 Provider 接受 6 位 code，内部做映射。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import akshare as ak  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from ..models import StockOhlcBar

log = logging.getLogger(__name__)


class StockHistoryFetchError(Exception):
    """历史 K 线抓取失败（含重试耗尽与空返回）"""


def to_sina_symbol(code: str) -> str:
    """6 位 A 股 code → 新浪 symbol（带 sh/sz/bj 前缀）

    规则覆盖：
      - 60 / 68 / 90 → sh（沪市主板/科创板/B 股）
      - 00 / 20 / 30 → sz（深市主板/B 股/创业板）
      - 43 / 82 / 83 / 87 / 88 / 92 → bj（北交所，含老两网与新板号）
      - 其他 → sh（fallback）
    """
    if code.startswith(('60', '68', '90')):
        return f'sh{code}'
    if code.startswith(('00', '20', '30')):
        return f'sz{code}'
    if code.startswith(('43', '82', '83', '87', '88', '92')):
        return f'bj{code}'
    return f'sh{code}'


@dataclass
class StockHistoryProvider:
    """封装 akshare 新浪日线接口 + 指数退避重试。

    输入 6 位 code，内部前缀化后调用 ak.stock_zh_a_daily。
    返回最新 days 个交易日的 OHLCV bars（前复权 qfq）。
    """
    max_retries: int = 3
    base_backoff: float = 0.5

    def fetch_history(self, code: str, days: int) -> list[StockOhlcBar]:
        symbol = to_sina_symbol(code)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                df: pd.DataFrame = ak.stock_zh_a_daily(
                    symbol=symbol,
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
            dt = row['date']
            d = dt.date() if hasattr(dt, 'date') else dt
            bars.append(StockOhlcBar(
                date=d,
                o=float(row['open']),
                h=float(row['high']),
                l=float(row['low']),
                c=float(row['close']),
                v=int(row['volume']),
            ))
        return bars
