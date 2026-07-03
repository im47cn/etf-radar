"""dapanyuntu 对账 QC (仅全市场): 自算 MA20 vs dapanyuntu 全市场均值.

巨潮 taxonomy 与东财不同源, 行业级无法 apples-to-apples, 故只对账全市场.
产出 market_breadth_qc.json; 偏差超阈仅 warning, 不阻断.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..output.writer import atomic_write_json

log = logging.getLogger(__name__)

THRESHOLD = 5.0  # 全市场 MA20 偏差百分点阈值; 方法学微差预期个位数


def _latest_point(market: list[dict[str, Any]]) -> tuple[str, float] | None:
    """market 序列中最后一个 rate 非 null 的 (date, rate)."""
    for p in reversed(market):
        if p.get('rate') is not None:
            return p['date'], float(p['rate'])
    return None


def reconcile(self_snapshot: dict[str, Any], dapanyuntu_snapshot: dict[str, Any],
              threshold: float = THRESHOLD) -> dict[str, Any]:
    """对账自算 MA20 全市场 vs dapanyuntu 全市场."""
    self_market = self_snapshot.get('periods', {}).get('ma20', {}).get('market', [])
    dpyt_market = dapanyuntu_snapshot.get('market', [])
    s = _latest_point(self_market)
    d = _latest_point(dpyt_market)
    abs_diff: float | None = None
    over = False
    if s is not None and d is not None:
        abs_diff = round(abs(s[1] - d[1]), 2)
        over = abs_diff > threshold
        if over:
            log.warning('全市场 MA20 对账偏差 %.2f 超阈 %.1f (self=%s@%s, dapanyuntu=%s@%s)',
                        abs_diff, threshold, s[1], s[0], d[1], d[0])
    return {
        'metric': 'ma20_market_reconcile',
        'threshold': threshold,
        'self': {'date': s[0], 'rate': s[1]} if s else None,
        'dapanyuntu': {'date': d[0], 'rate': d[1]} if d else None,
        'abs_diff': abs_diff,
        'over_threshold': over,
    }


def run(data_root: Path) -> Path | None:
    latest = Path(data_root) / 'latest'
    self_path = latest / 'market_temperature.json'
    dpyt_path = latest / 'market_breadth_qc_dapanyuntu.json'
    if not self_path.exists() or not dpyt_path.exists():
        log.info('对账跳过: 缺 %s 或 %s', self_path.name, dpyt_path.name)
        return None
    self_snapshot = json.loads(self_path.read_text(encoding='utf-8'))
    dpyt_snapshot = json.loads(dpyt_path.read_text(encoding='utf-8'))
    qc = reconcile(self_snapshot, dpyt_snapshot)
    out = latest / 'market_breadth_qc.json'
    atomic_write_json(out, qc)
    return out


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description='dapanyuntu 全市场 MA20 对账')
    p.add_argument('--data-root', type=Path, default=Path('data'))
    args = p.parse_args()
    run(args.data_root)


if __name__ == '__main__':
    main()
