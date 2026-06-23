"""ETF 持仓季度抓取管道。

入口:
- `python -m src.holdings_pipeline --data-root=./data --config-dir=./config`
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)


QUARTER_ENDS = [(3, 31), (6, 30), (9, 30), (12, 31)]


def candidate_quarters(today: date) -> list[date]:
    """生成最近 4 个季末日期（按降序），用于回退抓取。

    今日所在季度若已结束则纳入候选首位；否则首位是上一季末。
    """
    candidates: list[date] = []
    year = today.year
    while len(candidates) < 4:
        for m, d in reversed(QUARTER_ENDS):
            q = date(year, m, d)
            if q <= today:
                candidates.append(q)
                if len(candidates) >= 4:
                    break
        year -= 1
    return candidates
