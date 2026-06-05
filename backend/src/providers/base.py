"""Provider 抽象接口与异常"""
from typing import Protocol
import pandas as pd  # type: ignore[import-untyped]


class ProviderError(Exception):
    """数据源调用失败的基类"""


class EmptyDataError(ProviderError):
    """数据源返回空数据"""


class EtfDataProvider(Protocol):
    """统一 ETF 数据源接口"""

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        """返回标准化后的 OHLC DataFrame (调用方应再过 standardize_ohlc)"""
        ...
