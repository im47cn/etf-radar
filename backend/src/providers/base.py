"""Provider 抽象接口与异常"""
from typing import Protocol
import pandas as pd  # type: ignore[import-untyped]


class ProviderError(Exception):
    """数据源调用失败的基类"""


class EmptyDataError(ProviderError):
    """数据源返回空数据"""


class EtfDataProvider(Protocol):
    """统一 ETF 数据源接口"""

    name: str

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        """返回标准化后的 OHLC DataFrame (调用方应再过 standardize_ohlc)

        Args:
            symbol: ETF 代码 (如 'SOXX' 或 '512480')
            lookback_days: 回溯天数, 单位为**日历天**而非交易天。
                各 Provider 自行换算为合适的查询窗口。

        Returns:
            标准化后的 DataFrame, 已通过 standardize_ohlc 处理,
            含列 [date, open, high, low, close, volume, amount], date 为 UTC。
        """
        ...
