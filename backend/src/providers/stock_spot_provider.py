"""日频个股盘口快照 provider。

读取 data/holdings/*.json 取个股代码并集，一次性调
ak.stock_zh_a_spot_em 拿全市场快照，按代码过滤后写 stocks_spot.json。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import akshare as ak  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

log = logging.getLogger(__name__)


def collect_holdings_codes(holdings_dir: Path) -> set[str]:
    """扫描 holdings_dir 下所有 ETF 快照 JSON，收集 top_holdings 中的个股代码并集。

    跳过 index.json 与解析失败文件。
    """
    codes: set[str] = set()
    if not holdings_dir.exists():
        return codes
    for path in sorted(holdings_dir.glob('*.json')):
        if path.name == 'index.json':
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            for h in data.get('top_holdings', []):
                codes.add(str(h['code']))
        except (OSError, ValueError, KeyError) as e:
            log.warning(f'skip {path.name}: {e}')
    return codes


def build_stocks_spot_payload(
    spot_df: pd.DataFrame,
    target_codes: set[str],
) -> dict[str, Any]:
    """从全市场 spot DataFrame 过滤目标个股，构造 stocks_spot.json payload。

    akshare 字段:
        '代码', '名称', '最新价', '涨跌幅'（百分比单位，如 2.5 表示 +2.5%）
    """
    stocks: dict[str, dict[str, Any]] = {}
    if spot_df is None or spot_df.empty:
        return _envelope(stocks)

    filtered = spot_df[spot_df['代码'].isin(target_codes)]
    for _, row in filtered.iterrows():
        code = str(row['代码'])
        pct = row.get('涨跌幅')
        r_1d: float | None
        if pct is None or pd.isna(pct):
            r_1d = None
        else:
            r_1d = float(pct) / 100.0
        stocks[code] = {
            'name': str(row['名称']),
            'close': float(row['最新价']),
            'r_1d': r_1d,
        }
    return _envelope(stocks)


def _envelope(stocks: dict[str, Any]) -> dict[str, Any]:
    return {
        'schema_version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'stocks': stocks,
    }


def write_stocks_spot_snapshot(
    out_path: Path,
    holdings_dir: Path,
) -> None:
    """一次性调 spot 接口拉全市场，过滤后写 out_path。

    失败时写空 stocks 字典作为兜底，确保 nightly job 不中断。
    """
    codes = collect_holdings_codes(holdings_dir)
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        log.warning(f'stock_zh_a_spot_em failed: {e}')
        df = None

    payload = build_stocks_spot_payload(df, codes) if df is not None else _envelope({})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
