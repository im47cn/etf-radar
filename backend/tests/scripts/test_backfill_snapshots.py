"""backfill_snapshots 端到端测试 (mock provider)"""
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import jsonschema  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from scripts.backfill_snapshots import backfill

CONFIG_DIR = Path(__file__).parents[3] / 'config'


def _make_history(n: int = 300, base: float = 100.0) -> pd.DataFrame:
    """生成从 2025-09-01 起的 n 天 OHLC, 单调递增 close."""
    return pd.DataFrame({
        'date': pd.date_range('2025-09-01', periods=n, tz='UTC'),
        'open': [base] * n, 'high': [base * 1.01] * n, 'low': [base * 0.99] * n,
        'close': [base + i * 0.5 for i in range(n)],
        'volume': [10000] * n, 'amount': [base * 10000.0] * n,
    })


@patch('scripts.backfill_snapshots.AkshareEmProvider')
@patch('scripts.backfill_snapshots.YfinanceProvider')
def test_backfill_writes_snapshots_and_index(
    mock_yf: MagicMock, mock_ak: MagicMock,
) -> None:
    mock_yf.return_value.fetch_ohlc.return_value = _make_history()
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_history()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)

        # 回填 3 天 (其中至少包含 1 个交易日)
        backfill(
            start=date(2026, 1, 5), end=date(2026, 1, 8),
            data_root=data_root, config_dir=CONFIG_DIR,
            lookback_days=300, skip_existing=False,
        )

        snap_root = data_root / 'snapshots'
        snapshot_dirs = sorted(d.name for d in snap_root.iterdir() if d.is_dir())
        # 2026-01-05 (周一) 至 2026-01-08 (周四) 都是工作日
        assert len(snapshot_dirs) == 4

        # 每个 snapshot 含 4 个文件
        for date_str in snapshot_dirs:
            assert (snap_root / date_str / 'themes.json').exists()
            assert (snap_root / date_str / 'signals.json').exists()
            assert (snap_root / date_str / 'etfs.json').exists()
            assert (snap_root / date_str / 'meta.json').exists()

        # meta.json 标记 backfilled
        meta = json.loads((snap_root / snapshot_dirs[0] / 'meta.json').read_text())
        assert meta['backfilled'] is True

        # themes.json 含 21 主题 (14 原始 + 7 A 股独立行业)
        themes = json.loads((snap_root / snapshot_dirs[0] / 'themes.json').read_text())
        assert len(themes['themes']) == 21

        # snapshots-index.json 生成且含全部日期
        idx = json.loads((data_root / 'latest' / 'snapshots-index.json').read_text())
        idx_dates = [s['date'] for s in idx['snapshots']]
        assert idx_dates == snapshot_dirs


@patch('scripts.backfill_snapshots.AkshareEmProvider')
@patch('scripts.backfill_snapshots.YfinanceProvider')
def test_backfill_skip_existing(
    mock_yf: MagicMock, mock_ak: MagicMock,
) -> None:
    mock_yf.return_value.fetch_ohlc.return_value = _make_history()
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_history()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)

        # 第一次回填: 写 2 天
        backfill(
            start=date(2026, 1, 5), end=date(2026, 1, 6),
            data_root=data_root, config_dir=CONFIG_DIR,
            lookback_days=300, skip_existing=False,
        )
        first_count = sum(1 for _ in (data_root / 'snapshots').iterdir())

        # 写入哨兵字符串到既有 themes.json, 验证 skip_existing 不覆盖
        sentinel_path = data_root / 'snapshots' / '2026-01-05' / 'themes.json'
        sentinel_path.write_text('SENTINEL', encoding='utf-8')

        # 第二次回填, skip_existing=True
        backfill(
            start=date(2026, 1, 5), end=date(2026, 1, 8),
            data_root=data_root, config_dir=CONFIG_DIR,
            lookback_days=300, skip_existing=True,
        )

        # 已存在的 2026-01-05 不被覆盖
        assert sentinel_path.read_text(encoding='utf-8') == 'SENTINEL'
        # 新增 2026-01-07, 2026-01-08
        new_count = sum(1 for _ in (data_root / 'snapshots').iterdir())
        assert new_count == first_count + 2


@patch('scripts.backfill_snapshots.AkshareEmProvider')
@patch('scripts.backfill_snapshots.YfinanceProvider')
def test_backfill_output_schemas_valid(
    mock_yf: MagicMock, mock_ak: MagicMock,
) -> None:
    """回填产物应通过现有 JSON schemas 校验"""
    mock_yf.return_value.fetch_ohlc.return_value = _make_history()
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_history()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        schemas_root = Path(__file__).parent.parent / 'schemas'

        backfill(
            start=date(2026, 1, 5), end=date(2026, 1, 6),
            data_root=data_root, config_dir=CONFIG_DIR,
            lookback_days=300, skip_existing=False,
        )

        # 检查 themes/signals/etfs/meta 4 个 schema
        for kind in ('themes', 'signals', 'etfs', 'meta'):
            schema = json.loads((schemas_root / f'{kind}.schema.json').read_text())
            for d_dir in (data_root / 'snapshots').iterdir():
                if d_dir.is_dir():
                    data = json.loads((d_dir / f'{kind}.json').read_text())
                    jsonschema.validate(data, schema)
