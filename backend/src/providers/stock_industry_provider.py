"""个股 → 巨潮行业分类 (大类/中类) 数据源.

M0 spike 定源: 东财/申万接口 CI 不可用, 巨潮 stock_industry_change_cninfo
是唯一本机确认可用的个股成分源. 逐股调用, 返回含多分类标准多行 (巨潮/中证/旧版),
本模块筛"最新巨潮标准"一行, 取 行业门类(L1,~11 GICS式)/行业大类(L2,~86).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from .base import ProviderError

log = logging.getLogger(__name__)

_STD = '巨潮行业分类标准'


class StockIndustryFetchError(ProviderError):
    """单股行业拉取失败."""


def parse_industry(df: pd.DataFrame) -> dict[str, str] | None:
    """从 stock_industry_change_cninfo 返回的多标准多行中, 取最新巨潮标准.

    Returns {'l1': 行业大类, 'l2': 行业中类} 或 None (无巨潮归属).
    """
    if df is None or df.empty:
        return None
    if '分类标准' not in df.columns:
        return None
    cn = df[df['分类标准'] == _STD]
    if cn.empty:
        return None
    # 取变更日期最新一行 (稳定: 按日期排序取末尾)
    if '变更日期' in cn.columns:
        cn = cn.sort_values('变更日期')
    row = cn.iloc[-1]
    # 巨潮层级: 门类(~11 GICS式,一级) > 大类(~86,二级) > 中类(三级)
    l1 = row.get('行业门类')
    l2 = row.get('行业大类')
    if not l1 or not l2 or pd.isna(l1) or pd.isna(l2):
        return None
    return {'l1': str(l1), 'l2': str(l2)}


def fetch_stock_industry(code: str, _ak: Any = None, retries: int = 3, delay: float = 1.0) -> dict[str, str] | None:
    """拉单股巨潮行业; 重试后仍失败抛 StockIndustryFetchError.

    巨潮接口 5531 只规模下有瞬时抖动, 单股小重试提升整体覆盖率.
    _ak 供测试注入; 生产用 akshare.
    """
    import time

    ak_mod = _ak
    if ak_mod is None:
        import akshare as ak_mod  # type: ignore[import-untyped,no-redef]
    last: Exception | None = None
    for attempt in range(retries):
        try:
            df = ak_mod.stock_industry_change_cninfo(symbol=code)
            return parse_industry(df)
        except Exception as e:  # noqa: BLE001 — 统一包装为 provider 错误
            last = e
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    raise StockIndustryFetchError(f'{code}: {last}')
