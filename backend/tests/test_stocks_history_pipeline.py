"""backfill pipeline 端到端测试（mock provider）"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.models import StockOhlcBar
from src.stocks_history_pipeline import (
    BackfillReport,
    _guard_no_regress,
    main,
    run_archive_backfill,
    run_history_backfill,
    slice_bars_by_year,
)


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


def test_guard_no_regress_keeps_newer_daily_tail(tmp_path: Path):
    """现有 series 末位晚于 backfill 末位 → 保留 daily 已写入的最新格, 不回退."""
    existing = tmp_path / 'close_series.json'
    existing.write_text(json.dumps({
        'dates': ['2026-01-01', '2026-01-02', '2026-01-03'],  # daily 已 append 到 01-03
        'stocks': {'A': [10.0, 11.0, 12.0], 'B': [20.0, 21.0, 22.0]},
    }))
    # backfill 只算到 01-02 (历史接口当日未 roll)
    new_dates = [date(2026, 1, 1), date(2026, 1, 2)]
    new_matrix = {'A': [10.0, 11.0], 'B': [20.0, 21.0]}

    dates, matrix = _guard_no_regress(existing, new_dates, new_matrix, days=75)

    assert dates == ['2026-01-01', '2026-01-02', '2026-01-03']  # 01-03 被保留
    assert matrix['A'] == [10.0, 11.0, 12.0]
    assert matrix['B'] == [20.0, 21.0, 22.0]


def test_guard_no_regress_passthrough_when_not_older(tmp_path: Path):
    """backfill 末位 >= 现有末位 → 原样覆盖, 无 tail 拼接."""
    existing = tmp_path / 'close_series.json'
    existing.write_text(json.dumps({
        'dates': ['2026-01-01', '2026-01-02'],
        'stocks': {'A': [10.0, 11.0]},
    }))
    new_dates = [date(2026, 1, 2), date(2026, 1, 3)]  # backfill 更新, 含 01-03
    new_matrix = {'A': [11.5, 12.0]}

    dates, matrix = _guard_no_regress(existing, new_dates, new_matrix, days=75)

    assert dates == ['2026-01-02', '2026-01-03']
    assert matrix == {'A': [11.5, 12.0]}


def test_guard_no_regress_no_existing_file(tmp_path: Path):
    """首次 backfill (无现有文件) → 直接返回新数据."""
    new_dates = [date(2026, 1, 1), date(2026, 1, 2)]
    new_matrix = {'A': [10.0, 11.0]}
    dates, matrix = _guard_no_regress(
        tmp_path / 'missing.json', new_dates, new_matrix, days=75)
    assert dates == ['2026-01-01', '2026-01-02']
    assert matrix == new_matrix


# ---- 按年分片归档 (--archive) ----

def _bars_spanning_years() -> list[StockOhlcBar]:
    """跨 3 年的 bars: 2025-12-30..31, 2026-01-02..05 (跳过 01-01 元旦, 模拟缺失日)."""
    dates = [date(2025, 12, 30), date(2025, 12, 31),
             date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 5)]
    return [StockOhlcBar(
        date=d, o=10.0, h=10.5, l=9.5, c=10.0 + i * 0.1, v=1000,
    ) for i, d in enumerate(dates)]


def test_slice_bars_by_year_splits_and_aligns():
    shards = slice_bars_by_year({'002129': _bars_spanning_years()})
    assert sorted(shards) == [2025, 2026]
    s25, s26 = shards[2025], shards[2026]
    assert [d.isoformat() for d in s25.dates] == ['2025-12-30', '2025-12-31']
    assert [d.isoformat() for d in s26.dates] == ['2026-01-02', '2026-01-03', '2026-01-05']
    row25 = s25.closes['002129']
    row26 = s26.closes['002129']
    assert row25 == [10.0, 10.1]
    assert row26 == [10.2, 10.3, 10.4]
    # 跨 code 对齐: 'b' 只有 01-04 一根 bar, 2026 分片日期并集后其余日 None
    shards2 = slice_bars_by_year({
        '002129': _bars_spanning_years(),
        'b': [StockOhlcBar(date=date(2026, 1, 4), o=1, h=1, l=1, c=1.0, v=1)],
    })
    assert [d.isoformat() for d in shards2[2026].dates] ==         ['2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05']
    assert shards2[2026].closes['002129'] == [10.2, 10.3, None, 10.4]
    assert shards2[2026].closes['b'] == [None, None, 1.0, None]
    # 'b' 缺整个 2025 年 -> 2025 分片也要有对齐行 (全 None)
    assert shards2[2025].closes['b'] == [None, None]


def test_run_archive_backfill_writes_year_shards(tmp_path: Path):
    out_dir = tmp_path / 'stocks'

    with patch('src.stocks_history_pipeline._fetch_universe',
               return_value=['002129']), \
         patch('src.providers.stock_history_provider.StockHistoryProvider.fetch_history',
               new=lambda self, code, days: _bars_spanning_years()):
        report = run_archive_backfill(out_dir, max_workers=2)

    assert report.success_count == 1
    hist = out_dir / 'history'
    names = sorted(p.name for p in hist.glob('close_*.json'))
    assert names == ['close_2025.json', 'close_2026.json']
    data = json.loads((hist / 'close_2026.json').read_text())
    assert data['schema_version'] == '1.0'
    assert data['year'] == '2026'
    assert data['dates'] == ['2026-01-02', '2026-01-03', '2026-01-05']
    assert len(data['stocks']['002129']) == 3
    # 生产滚动文件不被归档触碰
    assert not (out_dir / 'close_series.json').exists()


def test_run_archive_years_only_current_skips_past_years(tmp_path: Path):
    out_dir = tmp_path / 'stocks'
    hist = out_dir / 'history'
    hist.mkdir(parents=True)
    frozen = {'schema_version': '1.0', 'generated_at': 'x', 'year': '2025',
              'dates': ['2025-12-30'], 'stocks': {'002129': [10.0]}}
    (hist / 'close_2025.json').write_text(json.dumps(frozen))

    with patch('src.stocks_history_pipeline._fetch_universe',
               return_value=['002129']), \
         patch('src.providers.stock_history_provider.StockHistoryProvider.fetch_history',
               new=lambda self, code, days: _bars_spanning_years()):
        run_archive_backfill(out_dir, max_workers=2,
                             years_only_current=True, today=date(2026, 1, 5))

    # 往年文件原样 (不 touch)
    assert json.loads((hist / 'close_2025.json').read_text()) == frozen
    assert (hist / 'close_2026.json').exists()


def test_run_archive_current_year_guard_keeps_newer_tail(tmp_path: Path):
    """归档结果末位旧于现有分片末位时, 护栏保留更新的尾部格 (daily 类比场景)."""
    out_dir = tmp_path / 'stocks'
    hist = out_dir / 'history'
    hist.mkdir(parents=True)
    existing = {'schema_version': '1.0', 'generated_at': 'x', 'year': '2026',
                'dates': ['2026-01-02', '2026-01-03', '2026-01-06'],
                'stocks': {'002129': [10.2, 10.3, 99.9]}}
    (hist / 'close_2026.json').write_text(json.dumps(existing))

    with patch('src.stocks_history_pipeline._fetch_universe',
               return_value=['002129']), \
         patch('src.providers.stock_history_provider.StockHistoryProvider.fetch_history',
               new=lambda self, code, days: _bars_spanning_years()):
        run_archive_backfill(out_dir, max_workers=2,
                             years_only_current=True, today=date(2026, 1, 6))

    data = json.loads((hist / 'close_2026.json').read_text())
    # 01-06 (来自现有文件) 被拼回, 01-05 之后
    assert data['dates'][-1] == '2026-01-06'
    assert data['stocks']['002129'][-1] == 99.9


def test_run_archive_all_fetch_failed_early_return(tmp_path: Path):
    """全量 fetch 失败 -> 空结果早退, 不写任何分片."""
    def boom(self, code, days):
        raise RuntimeError('sina down')

    with patch('src.stocks_history_pipeline._fetch_universe',
               return_value=['002129']), \
         patch('src.providers.stock_history_provider.StockHistoryProvider.fetch_history',
               new=boom):
        report = run_archive_backfill(tmp_path / 'stocks', max_workers=2)

    assert report.failed_count == 1
    assert not list((tmp_path / 'stocks' / 'history').glob('*.json'))


def test_cli_archive_flag_routes_to_archive(tmp_path: Path):
    """--archive CLI 分支路由到 run_archive_backfill (默认分支回归 run_history_backfill)."""
    calls = {}

    def fake_archive(out_dir, max_workers=4, years_only_current=False, today=None):
        calls['archive'] = (out_dir, max_workers, years_only_current)
        return BackfillReport()

    with patch('sys.argv', ['prog', '--data-root', str(tmp_path / 'data'),
                            '--archive', '--years-only-current', '--max-workers', '8']), \
         patch('src.stocks_history_pipeline.run_archive_backfill', new=fake_archive):
        main()

    out_dir, workers, only_current = calls['archive']
    assert out_dir == tmp_path / 'data' / 'stocks'
    assert workers == 8
    assert only_current is True
