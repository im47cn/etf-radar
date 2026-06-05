"""把 yfinance / akshare 的 DataFrame 列名/时区/类型统一"""
from typing import Literal
import pandas as pd  # type: ignore[import-untyped]

STANDARD_COLUMNS: list[str] = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']

YFINANCE_MAP: dict[str, str] = {
    'Date': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low',
    'Close': 'close', 'Adj Close': 'close', 'Volume': 'volume',
}

AKSHARE_MAP: dict[str, str] = {
    '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low',
    '收盘': 'close', '成交量': 'volume', '成交额': 'amount',
}


def standardize_ohlc(
    df: pd.DataFrame,
    source: Literal['yfinance', 'akshare'],
) -> pd.DataFrame:
    if source == 'yfinance':
        mapping = YFINANCE_MAP
    elif source == 'akshare':
        mapping = AKSHARE_MAP
    else:
        raise ValueError(f'unknown source: {source}')

    if df.index.name is not None and df.index.name in mapping:
        df = df.reset_index()

    df = df.rename(columns=mapping)
    if 'amount' not in df.columns:
        df['amount'] = pd.NA
    df['date'] = pd.to_datetime(df['date'], utc=True)
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df[STANDARD_COLUMNS].sort_values('date').reset_index(drop=True)
