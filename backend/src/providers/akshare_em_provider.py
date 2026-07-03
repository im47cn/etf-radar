"""akshare 数据源 — A 股场内 ETF"""
import time
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd  # type: ignore[import-untyped]
import akshare as ak  # type: ignore[import-untyped]
from .base import EtfDataProvider, ProviderError, EmptyDataError
from ._http_retry import install_requests_retry
from ..etl.standardize import standardize_ohlc

log = logging.getLogger(__name__)
BJT = ZoneInfo('Asia/Shanghai')

# akshare 内部裸 requests.get 无连接重试, eastmoney 间歇性 RemoteDisconnected 会直接失败.
# 模块加载即注入带 urllib3 Retry 的 session, 抵御掉连接. (幂等, sina provider 复用同一注入)
install_requests_retry()


class AkshareEmProvider(EtfDataProvider):
    """A 股场内 ETF 数据源 (东方财富, 通过 akshare)."""

    name = 'akshare-em'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        # 用 BJT 时区确定 A 股市场的"今天" (避免 UTC 服务器 off-by-one)
        end = datetime.now(tz=BJT).date()
        start = end - timedelta(days=int(lookback_days * 1.6))  # 含周末+节假日缓冲
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                df = ak.fund_etf_hist_em(
                    symbol=symbol,
                    period='daily',
                    start_date=start.strftime('%Y%m%d'),
                    end_date=end.strftime('%Y%m%d'),
                    adjust='qfq',
                )
                if df is None or df.empty:
                    raise EmptyDataError(f'akshare empty for {symbol}')
                return standardize_ohlc(df, source='akshare')
            except EmptyDataError:
                raise
            except Exception as e:
                last_exc = e
                log.warning(f'akshare attempt {attempt+1} failed for {symbol}: {e}')
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        raise ProviderError(f'akshare failed after {self.max_retries} retries: {last_exc}')
