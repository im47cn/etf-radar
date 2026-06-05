"""yfinance 数据源 — 美股 ETF"""
import time
import logging
import pandas as pd  # type: ignore[import-untyped]
import yfinance as yf  # type: ignore[import-untyped]
from .base import EtfDataProvider, ProviderError, EmptyDataError
from ..etl.standardize import standardize_ohlc

log = logging.getLogger(__name__)


class YfinanceProvider(EtfDataProvider):
    """美股 ETF 数据源 (Yahoo Finance, 延迟 ~15 分钟).

    使用 auto_adjust=True, Close 列即复权后价格, 与 standardize_ohlc 的约定一致。
    """

    name = 'yfinance'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=f'{lookback_days}d', auto_adjust=True)
                if df.empty:
                    raise EmptyDataError(f'yfinance returned empty for {symbol}')
                return standardize_ohlc(df, source='yfinance')
            except EmptyDataError:
                raise
            except Exception as e:
                last_exc = e
                log.warning(f'yfinance attempt {attempt+1} failed for {symbol}: {e}')
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        raise ProviderError(f'yfinance failed after {self.max_retries} retries: {last_exc}')
