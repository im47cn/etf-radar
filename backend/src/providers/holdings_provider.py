"""akshare fund_portfolio_hold_em 封装。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import akshare as ak  # type: ignore[import-untyped]

from ..models import EtfHoldingsSnapshot, EtfTopHolding

log = logging.getLogger(__name__)


class HoldingsFetchError(Exception):
    """持仓抓取失败（空数据 / 网络 / 字段缺失等）。"""


class HoldingsProvider:
    name = 'akshare-fund-portfolio-hold-em'

    def fetch(
        self,
        etf_code: str,
        etf_name: str,
        quarter: date,
    ) -> EtfHoldingsSnapshot:
        """抓取单只 ETF 在指定季度的 top-10 持仓。

        akshare 真实 API: fund_portfolio_hold_em(symbol=代码, date=年份)
        返回该年度全部季度的持仓行，需要按 `季度` 列过滤到目标季度。

        空 DataFrame / 异常 / 缺字段一律 raise HoldingsFetchError，
        上层 holdings_pipeline 负责候选季度回退。
        """
        year_str = str(quarter.year)
        quarter_num = (quarter.month - 1) // 3 + 1  # 3→1, 6→2, 9→3, 12→4
        quarter_tag = f'{quarter.year}年{quarter_num}季度'
        try:
            df = ak.fund_portfolio_hold_em(symbol=etf_code, date=year_str)
        except Exception as e:
            raise HoldingsFetchError(f'{etf_code} {quarter_tag}: {e}') from e

        if df is None or df.empty:
            raise HoldingsFetchError(f'{etf_code} {quarter_tag}: empty')

        required = {'股票代码', '股票名称', '占净值比例', '季度'}
        if not required.issubset(df.columns):
            raise HoldingsFetchError(
                f'{etf_code} {quarter_tag}: missing columns, got {list(df.columns)}'
            )

        df = df[df['季度'].str.startswith(quarter_tag, na=False)]
        if df.empty:
            raise HoldingsFetchError(f'{etf_code} {quarter_tag}: quarter not disclosed')

        df = df.sort_values('占净值比例', ascending=False).head(10)
        holdings = [
            EtfTopHolding(
                code=str(row['股票代码']),
                name=str(row['股票名称']),
                weight=float(row['占净值比例']),
            )
            for _, row in df.iterrows()
        ]

        return EtfHoldingsSnapshot(
            etf_code=etf_code,
            etf_name=etf_name,
            disclosure_date=quarter,
            fetched_at=datetime.now(timezone.utc),
            top_holdings=holdings,
        )
