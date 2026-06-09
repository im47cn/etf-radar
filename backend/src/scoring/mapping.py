"""映射分 — 美股 vs A 股 ETF 的对齐 60d 相关性 × 100"""
import math
import pandas as pd  # type: ignore[import-untyped]
from scipy.stats import pearsonr  # type: ignore[import-untyped]


def _log_returns(df: pd.DataFrame) -> pd.DataFrame:
    """计算单只 ETF 的逐日对数收益, 丢弃首行 (无前一日参考)。"""
    df = df.sort_values('date').copy()
    df['log_ret'] = (df['close'] / df['close'].shift(1)).apply(
        lambda x: math.log(x) if x and x > 0 else None
    )
    return df.dropna(subset=['log_ret'])


def _align_log_returns(us: pd.DataFrame, cn: pd.DataFrame) -> pd.DataFrame:
    """按交易日 intersection 对齐美股+A 股的对数收益。"""
    us_r = _log_returns(us)[['date', 'log_ret']].rename(columns={'log_ret': 'us'})
    cn_r = _log_returns(cn)[['date', 'log_ret']].rename(columns={'log_ret': 'cn'})
    us_r['date'] = us_r['date'].dt.normalize()
    cn_r['date'] = cn_r['date'].dt.normalize()
    return us_r.merge(cn_r, on='date', how='inner')


def mapping_score(
    us_ohlc: pd.DataFrame,
    cn_ohlc: pd.DataFrame,
    window: int,
    min_aligned: int,
) -> int | None:
    """对齐后取最近 window 天计算 Pearson corr, 返回 |corr| × 100 (整数 0-100)。

    Args:
        us_ohlc: 美股 ETF 的 OHLC DataFrame, 含 date/close 列
        cn_ohlc: A 股 ETF 的 OHLC DataFrame, 含 date/close 列
        window: 滚动窗口长度 (日历日)
        min_aligned: 最少对齐日数, 不足返回 None

    Returns:
        映射分 0-100 (整数), 或 None (数据不足/相关性 NaN)
    """
    aligned = _align_log_returns(us_ohlc, cn_ohlc)
    aligned = aligned.tail(window)
    if len(aligned) < min_aligned:
        return None
    corr, _ = pearsonr(aligned['us'], aligned['cn'])
    if math.isnan(corr):
        return None
    return int(round(abs(corr) * 100))
