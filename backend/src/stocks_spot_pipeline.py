"""个股 spot 独立刷新管道。

入口:
- `python -m src.stocks_spot_pipeline --data-root=./data`

读取 data/holdings/*.json 的个股代码并集，调 akshare 全市场快照，
写 data/latest/stocks_spot.json。

与主 pipeline 解耦：spot 失败不影响 themes/etfs/signals/meta 时间戳。
GitHub Actions cron 由 .github/workflows/stocks-spot-refresh.yml 触发。
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .providers.stock_spot_provider import write_stocks_spot_snapshot

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    out_path = args.data_root / 'latest' / 'stocks_spot.json'
    holdings_dir = args.data_root / 'holdings'
    write_stocks_spot_snapshot(out_path=out_path, holdings_dir=holdings_dir)
    log.info(f'stocks_spot done: {out_path}')


if __name__ == '__main__':
    main()
