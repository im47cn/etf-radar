"""backfill pipeline 端到端测试（mock provider）"""
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import StockOhlcBar
from src.stocks_history_pipeline import run_history_backfill


def _bars(code: str, n: int = 75) -> list[StockOhlcBar]:
    base = date(2026, 1, 1).toordinal()
    return [
        StockOhlcBar(
            date=date.fromordinal(base + i),
            o=10.0 + i * 0.1, h=10.5 + i * 0.1, l=9.5 + i * 0.1,
            c=10.2 + i * 0.1, v=1000000 + i * 1000,
        )
        for i in range(n)
    ]


def test_backfill_writes_close_volume_series(tmp_path: Path):
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / '512480.json').write_text(json.dumps({
        'etf_code': '512480', 'etf_name': 'x',
        'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'TCL中环', 'weight': 8.5}],
    }))
    out_dir = tmp_path / 'stocks'

    fake_universe = ['002129', '603501']

    def fake_fetch(self, code, days):
        return _bars(code, days)

    with patch('src.stocks_history_pipeline._fetch_universe', return_value=fake_universe), \
         patch('src.providers.stock_history_provider.StockHistoryProvider.fetch_history', new=fake_fetch):
        report = run_history_backfill(
            holdings_dir=holdings_dir, out_dir=out_dir, days=75, max_workers=2,
        )

    assert (out_dir / 'close_series.json').exists()
    assert (out_dir / 'volume_series.json').exists()
    assert (out_dir / 'ohlc' / '002129.json').exists()
    # 603501 不在 holdings 内 → 不应写 ohlc
    assert not (out_dir / 'ohlc' / '603501.json').exists()
    assert report.success_count == 2
    assert report.failed_count == 0

    close_data = json.loads((out_dir / 'close_series.json').read_text())
    assert len(close_data['dates']) == 75
    assert '002129' in close_data['stocks']
    assert len(close_data['stocks']['002129']) == 75


def test_backfill_isolates_per_stock_failure(tmp_path: Path):
    (tmp_path / 'holdings').mkdir()
    (tmp_path / 'holdings' / 'x.json').write_text(json.dumps({
        'etf_code': 'x', 'etf_name': 'x', 'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00', 'top_holdings': [],
    }))

    def fake_fetch(self, code, days):
        if code == 'bad':
            from src.providers.stock_history_provider import StockHistoryFetchError
            raise StockHistoryFetchError('boom')
        return _bars(code, days)

    with patch('src.stocks_history_pipeline._fetch_universe', return_value=['ok1', 'bad', 'ok2']), \
         patch('src.providers.stock_history_provider.StockHistoryProvider.fetch_history', new=fake_fetch):
        report = run_history_backfill(
            holdings_dir=tmp_path / 'holdings',
            out_dir=tmp_path / 'stocks',
            days=75, max_workers=2,
        )

    assert report.success_count == 2
    assert report.failed_count == 1
    assert 'bad' in report.failed
