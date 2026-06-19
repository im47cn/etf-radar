"""akshare 新浪财经数据源 — A 股 ETF 备用源 (无前复权)"""
import time
import logging
import pandas as pd  # type: ignore[import-untyped]
import akshare as ak  # type: ignore[import-untyped]
from .base import EtfDataProvider, ProviderError, EmptyDataError
from ..etl.standardize import standardize_ohlc

log = logging.getLogger(__name__)


class AkshareSinaProvider(EtfDataProvider):
    """A 股场内 ETF 数据源 (新浪财经, 通过 akshare).

    注意:
    - sina 接口无 adjust 参数，返回**不复权**数据，与 EM 源前复权数据存在分红日跳跃差异。
    - 仅作为 EM 主源失败时的备用 fallback 使用。
    - sina 接口返回**全历史**数据，按 lookback_days 截尾。
    """

    name = 'akshare-sina'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        sina_symbol = self._to_sina_symbol(symbol)
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                df = ak.fund_etf_hist_sina(symbol=sina_symbol)
                if df is None or df.empty:
                    raise EmptyDataError(f'akshare-sina empty for {symbol}')
                df_recent = df.tail(int(lookback_days * 1.6))
                return standardize_ohlc(df_recent, source='akshare-sina')
            except EmptyDataError:
                raise
            except Exception as e:
                last_exc = e
                log.warning(f'akshare-sina attempt {attempt+1} failed for {symbol}: {e}')
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        raise ProviderError(f'akshare-sina failed after {self.max_retries} retries: {last_exc}')

    @staticmethod
    def _to_sina_symbol(em_symbol: str) -> str:
        """EM symbol → sina symbol prefix.

        深市 ETF: 159xxx, 162xxx → sz{symbol}
        沪市 ETF: 5xxxxx, 6xxxxx → sh{symbol}
        """
        if em_symbol.startswith('1'):
            return f'sz{em_symbol}'
        if em_symbol.startswith(('5', '6')):
            return f'sh{em_symbol}'
        raise ValueError(f'unknown CN ETF symbol prefix: {em_symbol}')
