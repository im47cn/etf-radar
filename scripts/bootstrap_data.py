"""首次种子数据: 拉一次 full 模式 pipeline 把 data/latest/ 填上。

用法:
    cd backend && uv run python ../scripts/bootstrap_data.py

需联网, 会从 yfinance + akshare 拉真实 OHLC。
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

from src.pipeline import PipelineMode, run_pipeline  # noqa: E402

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    run_pipeline(
        mode=PipelineMode.FULL,
        data_root=ROOT / 'data',
        config_dir=ROOT / 'config',
    )
    print(f'Bootstrap done. Files written to {ROOT / "data" / "latest"}')
