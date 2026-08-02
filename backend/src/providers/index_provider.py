"""A 股主要指数收盘价 Provider（基于 ak.stock_zh_index_daily，新浪源）

新浪指数 daily 源字段与个股一致 [date, open, high, low, close, volume]，
date 为日期型。指数前缀映射独立于个股: 000xxx → sh(上证系列), 399xxx → sz(深证系列)。
仅取收盘价 (指数无需 OHLCV 全量)，供温度页对比图叠加。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import akshare as ak  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from ._http_retry import install_requests_retry

log = logging.getLogger(__name__)

# akshare 内部裸 requests.get 无连接重试, 新浪源同样受益于全局重试注入 (见 _http_retry.py)
install_requests_retry()


class IndexFetchError(Exception):
    """指数点位抓取失败（含重试耗尽与空返回）"""


def to_index_symbol(code: str) -> str:
    """6 位指数代码 → 新浪 symbol (带 sh/sz 前缀).

    规则:
      - 000 开头 → sh (上证系列: 上证指数/沪深300/科创50/科创100 等)
      - 399 开头 → sz (深证系列: 深证成指/创业板指 等)
      - 其他 → sh (fallback)
    """
    if code.startswith('399'):
        return f'sz{code}'
    return f'sh{code}'


class IndexCloseProvider(Protocol):
    """指数收盘价数据源契约 (消费者依赖抽象, 便于测试注入伪实现)."""

    def fetch_close(self, code: str) -> list[tuple[date, float]]:
        """返回 [(date, close), ...] 升序收盘价序列."""
        ...


@dataclass
class IndexProvider:
    """封装 akshare 新浪指数日线 + 指数退避重试.

    输入 6 位指数代码, 返回 [(date, close), ...] 收盘价序列.
    """

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
                return self._df_to_close(df)
            except IndexFetchError:
                raise
            except Exception as e:  # noqa: BLE001  外部数据源兜底
                last_err = e
                if attempt < self.max_retries:
                    backoff = self.base_backoff * (2 ** attempt)
                    log.warning('%s retry %d after %gs: %s', code, attempt + 1, backoff, e)
                    time.sleep(backoff)
        raise IndexFetchError(f'{code} fetch failed: {last_err}')

    @staticmethod
    def _df_to_close(df: pd.DataFrame) -> list[tuple[date, float]]:
        rows: list[tuple[date, float]] = []
        for _, row in df.iterrows():
            d = pd.Timestamp(row['date']).date()
            rows.append((d, float(row['close'])))
        return rows
