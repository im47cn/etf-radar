"""A 股主要指数收盘价 Provider

两个独立源, 供 market_breadth.index_series 做 chain 逐级兜底 (CLAUDE.md 硬约束):
- IndexProvider (新浪 ak.stock_zh_index_daily): 稳定, 首选.
- EmIndexProvider (东财 ak.stock_zh_index_daily_em): 东财 push2his 间歇性
  RemoteDisconnected (见 data-fetch-resilience memory), 仅作兜底.

两源字段一致 [date, open, high, low, close, volume(, amount)], 仅取收盘价.
指数前缀映射: 000xxx → sh(上证系列), 399xxx → sz(深证系列), 与个股前缀映射独立.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date

import akshare as ak  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from ._http_retry import install_requests_retry

log = logging.getLogger(__name__)

# akshare 内部裸 requests.get 无连接重试, 新浪/东财均受益于全局重试注入 (见 _http_retry.py)
install_requests_retry()


class IndexFetchError(Exception):
    """指数点位抓取失败（含重试耗尽与空返回）"""


def to_index_symbol(code: str) -> str:
    """6 位指数代码 → 新浪/东财通用 symbol (带 sh/sz 前缀).

    规则:
      - 399 开头 → sz (深证系列: 深证成指/创业板指 等)
      - 其他(000 开头含上证指数/沪深300/科创50/科创100) → sh
    """
    if code.startswith('399'):
        return f'sz{code}'
    return f'sh{code}'


def _df_to_close(df: pd.DataFrame) -> list[tuple[date, float]]:
    """从指数日线 DataFrame 提取 [(date, close), ...]. 两源字段一致."""
    rows: list[tuple[date, float]] = []
    for _, row in df.iterrows():
        d = pd.Timestamp(row['date']).date()
        rows.append((d, float(row['close'])))
    return rows


@dataclass
class IndexProvider:
    """新浪指数日线 + 指数退避重试 (首选源)."""

    name: str = 'index-sina'
    max_retries: int = 3
    base_backoff: float = 0.5

    def fetch_close(self, code: str) -> list[tuple[date, float]]:
        symbol = to_index_symbol(code)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                df: pd.DataFrame = ak.stock_zh_index_daily(symbol=symbol)
                if df is None or df.empty:
                    raise IndexFetchError(f'{code}: empty dataframe')
                return _df_to_close(df)
            except IndexFetchError:
                raise
            except Exception as e:  # noqa: BLE001  外部数据源兜底
                last_err = e
                if attempt < self.max_retries:
                    backoff = self.base_backoff * (2 ** attempt)
                    log.warning('%s retry %d after %gs: %s', code, attempt + 1, backoff, e)
                    time.sleep(backoff)
        raise IndexFetchError(f'{code} sina fetch failed: {last_err}')


@dataclass
class EmIndexProvider:
    """东财指数日线 + 退避重试 (兜底源).

    东财 push2his 间歇性掐断连接, 重试次数压低 (1 次) 以便 chain 快速切换回退.
    """

    name: str = 'index-em'
    max_retries: int = 1
    base_backoff: float = 1.0

    def fetch_close(self, code: str) -> list[tuple[date, float]]:
        symbol = to_index_symbol(code)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                df = ak.stock_zh_index_daily_em(symbol=symbol)
                if df is None or df.empty:
                    raise IndexFetchError(f'{code}: empty dataframe')
                return _df_to_close(df)
            except IndexFetchError:
                raise
            except Exception as e:  # noqa: BLE001  外部数据源兜底
                last_err = e
                if attempt < self.max_retries:
                    backoff = self.base_backoff * (2 ** attempt)
                    log.warning('%s em retry %d after %gs: %s', code, attempt + 1, backoff, e)
                    time.sleep(backoff)
        raise IndexFetchError(f'{code} em fetch failed: {last_err}')
