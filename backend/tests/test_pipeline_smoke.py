import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd  # type: ignore[import-untyped]

from src.pipeline import PipelineMode, run_pipeline


def _make_fake_ohlc(n: int = 200, base: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.date_range('2025-01-01', periods=n, tz='UTC'),
        'open': [base] * n, 'high': [base * 1.01] * n, 'low': [base * 0.99] * n,
        'close': [base + i * 0.5 for i in range(n)],
        'volume': [10000] * n, 'amount': [base * 10000.0] * n,
    })


@patch('src.pipeline.AkshareEmProvider')
@patch('src.pipeline.YfinanceProvider')
def test_pipeline_full_mode_creates_files(
    mock_yf: MagicMock, mock_ak: MagicMock,
) -> None:
    mock_yf.return_value.fetch_ohlc.return_value = _make_fake_ohlc()
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_fake_ohlc()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        # config_dir 用项目真实的 config/ (含 14 themes)
        config_dir = Path(__file__).parent.parent.parent / 'config'
        run_pipeline(mode=PipelineMode.FULL, data_root=data_root, config_dir=config_dir)

        latest = data_root / 'latest'
        assert (latest / 'themes.json').exists()
        assert (latest / 'etfs.json').exists()
        assert (latest / 'signals.json').exists()
        assert (latest / 'meta.json').exists()

        themes = json.loads((latest / 'themes.json').read_text(encoding='utf-8'))
        assert len(themes['themes']) == 14
        assert themes['schema_version'] == '1.0'

        signals = json.loads((latest / 'signals.json').read_text(encoding='utf-8'))
        assert signals['summary']['themes_total'] == 14
        # All themes have same composite (mock returns same df) → top_theme should be deterministic

        meta = json.loads((latest / 'meta.json').read_text(encoding='utf-8'))
        assert meta['providers']['us']['status'] == 'ok'
        assert meta['providers']['cn']['status'] == 'ok'
        assert meta['failed_symbols'] == []


@patch('src.pipeline.AkshareEmProvider')
@patch('src.pipeline.YfinanceProvider')
def test_pipeline_marks_failed_providers(
    mock_yf: MagicMock, mock_ak: MagicMock,
) -> None:
    """模拟 US fetch 全部失败, meta.providers.us.status 应为 'degraded'"""
    from src.providers.base import ProviderError
    mock_yf.return_value.fetch_ohlc.side_effect = ProviderError('network')
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_fake_ohlc()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        config_dir = Path(__file__).parent.parent.parent / 'config'
        run_pipeline(mode=PipelineMode.FULL, data_root=data_root, config_dir=config_dir)

        meta = json.loads((data_root / 'latest' / 'meta.json').read_text(encoding='utf-8'))
        assert meta['providers']['us']['status'] == 'degraded'
        assert meta['providers']['cn']['status'] == 'ok'
        assert len(meta['failed_symbols']) > 0  # 至少有一些 US symbols 失败
