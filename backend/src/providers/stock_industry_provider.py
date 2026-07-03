"""个股 → 巨潮行业分类 (大类/中类) 数据源.

M0 spike 定源: 东财/申万接口 CI 不可用, 巨潮 stock_industry_change_cninfo
是唯一本机确认可用的个股成分源. 逐股调用, 返回含多分类标准多行 (巨潮/中证/旧版),
本模块筛"最新巨潮标准"一行, 取 行业大类(L1)/行业中类(L2).
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
    l1 = row.get('行业大类')
    l2 = row.get('行业中类')
    if not l1 or not l2 or pd.isna(l1) or pd.isna(l2):
        return None
    return {'l1': str(l1), 'l2': str(l2)}


def fetch_stock_industry(code: str, _ak: Any = None) -> dict[str, str] | None:
    """拉单股巨潮行业; 失败抛 StockIndustryFetchError.

    _ak 供测试注入; 生产用 akshare.
    """
    ak_mod = _ak
    if ak_mod is None:
        import akshare as ak_mod  # type: ignore[import-untyped,no-redef]
    try:
        df = ak_mod.stock_industry_change_cninfo(symbol=code)
    except Exception as e:  # noqa: BLE001 — 统一包装为 provider 错误
        raise StockIndustryFetchError(f'{code}: {e}') from e
    return parse_industry(df)
