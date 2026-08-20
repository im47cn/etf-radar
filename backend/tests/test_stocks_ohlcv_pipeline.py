"""OHLCV 归档管线测试（mock 数据源，禁真实网络）。"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.stocks_ohlcv_pipeline import (
    KEEP_DAYS,
    OhlcvBar,
    OhlcvFetchError,
    _df_to_bars,
    _load_existing,
    fetch_ohlcv,
    main,
    merge_bars,
    run_ohlcv_pipeline,
)


def _bar(d: str, c: float = 10.0, amt: float = 1e8) -> OhlcvBar:
    return OhlcvBar(d=d, o=c, h=c * 1.02, l=c * 0.98, c=c, v=1_000_000, amt=amt)


def _bars(n: int, start: date = date(2024, 1, 1)) -> list[OhlcvBar]:
    base = start.toordinal()
    return [_bar(date.fromordinal(base + i).isoformat(), c=10.0 + i) for i in range(n)]


def _fake_df(n: int = 2, start: str = '2026-04-01') -> pd.DataFrame:
    days = [date.fromordinal(date.fromisoformat(start).toordinal() + i) for i in range(n)]
    return pd.DataFrame({
        'date': pd.to_datetime(days),
        'open': [10.0 + i for i in range(n)],
        'high': [10.5 + i for i in range(n)],
        'low': [9.5 + i for i in range(n)],
        'close': [10.2 + i for i in range(n)],
        'volume': [1_000_000 + i for i in range(n)],
        'amount': [1.5e8 + i for i in range(n)],
    })


# ---- fetch_ohlcv (新浪日线 + 重试) ----

def test_fetch_ohlcv_success_includes_amount():
    captured: dict[str, str] = {}

    def fake_daily(symbol: str, adjust: str) -> pd.DataFrame:
        captured['symbol'], captured['adjust'] = symbol, adjust
        return _fake_df()

    with patch('akshare.stock_zh_a_daily', side_effect=fake_daily):
        bars = fetch_ohlcv('600519', days=60)
    assert captured == {'symbol': 'sh600519', 'adjust': 'qfq'}
    assert len(bars) == 2
    assert bars[0].d == '2026-04-01'
    assert bars[0].c == 10.2
    assert bars[0].v == 1_000_000
    assert bars[0].amt == 1.5e8  # spec §2.2: bars 必须含成交额


def test_fetch_ohlcv_empty_df_raises_without_retry():
    with patch('akshare.stock_zh_a_daily', return_value=pd.DataFrame()), \
         pytest.raises(OhlcvFetchError, match='empty'):
        fetch_ohlcv('600519', max_retries=2)


def test_fetch_ohlcv_retries_then_succeeds():
    calls = [0]

    def flaky(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            raise ConnectionError('network')
        return _fake_df()

    with patch('akshare.stock_zh_a_daily', side_effect=flaky):
        bars = fetch_ohlcv('600519', max_retries=2, base_backoff=0.001)
    assert calls[0] == 2
    assert len(bars) == 2


def test_fetch_ohlcv_exhausts_retries():
    with patch('akshare.stock_zh_a_daily', side_effect=ConnectionError('down')), \
         pytest.raises(OhlcvFetchError, match='fetch failed'):
        fetch_ohlcv('600519', max_retries=1, base_backoff=0.001)


def test_fetch_ohlcv_truncates_to_days():
    with patch('akshare.stock_zh_a_daily', return_value=_fake_df(n=10)):
        bars = fetch_ohlcv('600519', days=3)
    assert len(bars) == 3
    assert bars[-1].c == 10.2 + 9  # 截尾部: 保留最后 3 行


# ---- _df_to_bars 数据护栏 ----

def test_df_to_bars_skips_bad_rows():
    nan = float('nan')
    df = pd.DataFrame({
        'date': pd.to_datetime(['2026-04-01', '2026-04-02', '2026-04-03', '2026-04-04', '2026-04-05']),
        'open': [10.0, nan, 10.0, 10.0, 10.0],
        'high': [10.5, 10.5, 10.5, 10.5, 10.5],
        'low': [9.5, 9.5, 9.5, 9.5, 9.5],
        'close': [10.2, 10.2, -1.0, 10.2, 10.2],   # 第3行 c<=0 (qfq 老股护栏)
        'volume': [1000, 1000, 1000, 1000, None],   # 第5行解析异常 (None→TypeError)
        'amount': [1e8, 1e8, 1e8, 1e8, 1e8],
    })
    bars = _df_to_bars('600519', df, days=10)
    assert [b.d for b in bars] == ['2026-04-01', '2026-04-04']


def test_df_to_bars_accepts_str_date_column():
    df = pd.DataFrame({
        'date': ['2026-04-01'],
        'open': [10.0], 'high': [10.5], 'low': [9.5], 'close': [10.2],
        'volume': [1000], 'amount': [1e8],
    })
    bars = _df_to_bars('600519', df, days=1)
    assert bars[0].d == '2026-04-01'


# ---- merge_bars 防回退护栏 ----

def test_merge_same_day_new_wins():
    existing = [_bar('2026-04-01', c=10.0)]
    new = [_bar('2026-04-01', c=11.0)]
    merged = merge_bars(existing, new)
    assert len(merged) == 1 and merged[0].c == 11.0


def test_merge_keeps_newer_existing_tail():
    """拉取结果只到 04-02 而现有已含 04-03 → 04-03 保留, 不回退 (护栏核心)."""
    existing = [_bar('2026-04-01'), _bar('2026-04-02'), _bar('2026-04-03')]
    new = [_bar('2026-04-01'), _bar('2026-04-02')]
    merged = merge_bars(existing, new)
    assert [b.d for b in merged] == ['2026-04-01', '2026-04-02', '2026-04-03']


def test_merge_truncates_window_and_sorts():
    existing = _bars(300, start=date(2022, 1, 1))       # 2022 起的旧段
    new = _bars(300, start=date(2023, 6, 1))            # 与旧段重叠的更新段
    merged = merge_bars(existing, new, keep=400)
    assert len(merged) == 400
    assert merged == sorted(merged, key=lambda b: b.d)  # 升序
    assert merged[-1].d == date.fromordinal(date(2023, 6, 1).toordinal() + 299).isoformat()


# ---- _load_existing 容错 ----

def test_load_existing_missing_file(tmp_path: Path):
    assert _load_existing(tmp_path / 'nope.json') == []


def test_load_existing_corrupt_file_treated_as_empty(tmp_path: Path):
    p = tmp_path / '600519.json'
    p.write_text('{broken', encoding='utf-8')
    assert _load_existing(p) == []


def test_load_existing_parses_and_skips_bad_rows(tmp_path: Path):
    p = tmp_path / '600519.json'
    good = {'d': '2026-04-01', 'o': 10.0, 'h': 10.5, 'l': 9.5,
            'c': 10.2, 'v': 1000, 'amt': 1e8}
    p.write_text(json.dumps({
        'schema_version': '1.0', 'code': '600519',
        'bars': [good, {'d': '2026-04-02'}],  # 第2行缺字段 → 跳过
    }), encoding='utf-8')
    bars = _load_existing(p)
    assert len(bars) == 1 and bars[0].d == '2026-04-01' and bars[0].amt == 1e8


# ---- run_ohlcv_pipeline 端到端 (mock fetch) ----

def test_run_writes_per_code_files(tmp_path: Path):
    out_dir = tmp_path / 'ohlcv'

    def fake_fetch(code: str, days: int):
        return _bars(days)

    with patch('src.stocks_ohlcv_pipeline.fetch_ohlcv', side_effect=fake_fetch):
        report = run_ohlcv_pipeline(out_dir, codes=['600519', '000001'], max_workers=2)

    assert report.success_count == 2 and report.failed_count == 0
    data = json.loads((out_dir / '600519.json').read_text(encoding='utf-8'))
    assert data['schema_version'] == '1.0'
    assert data['code'] == '600519'
    assert len(data['bars']) == KEEP_DAYS
    bar = data['bars'][-1]
    assert set(bar) == {'d', 'o', 'h', 'l', 'c', 'v', 'amt'}  # spec §2.2 键集
    assert [b['d'] for b in data['bars']] == sorted(b['d'] for b in data['bars'])


def test_run_merges_with_existing_no_regress(tmp_path: Path):
    out_dir = tmp_path / 'ohlcv'
    out_dir.mkdir()
    # 现有文件末位 04-30 (增量已写入), 拉取结果只到 04-29
    (out_dir / '600519.json').write_text(json.dumps({
        'schema_version': '1.0', 'code': '600519',
        'bars': [
            {'d': '2026-04-29', 'o': 10, 'h': 10, 'l': 10, 'c': 10, 'v': 1, 'amt': 1},
            {'d': '2026-04-30', 'o': 11, 'h': 11, 'l': 11, 'c': 11, 'v': 1, 'amt': 1},
        ],
    }), encoding='utf-8')

    with patch('src.stocks_ohlcv_pipeline.fetch_ohlcv',
               side_effect=lambda code, days: [
                   _bar('2026-04-29', c=10.5),  # 同日刷新
                   _bar('2026-04-28', c=9.0),
               ]):
        report = run_ohlcv_pipeline(out_dir, codes=['600519'])

    assert report.success_count == 1
    bars = json.loads((out_dir / '600519.json').read_text(encoding='utf-8'))['bars']
    assert [b['d'] for b in bars] == ['2026-04-28', '2026-04-29', '2026-04-30']
    assert bars[1]['c'] == 10.5          # 同日新值覆盖
    assert bars[2]['c'] == 11            # 现有更新尾部保留 (防回退)


def test_run_isolates_failure(tmp_path: Path):
    def fake_fetch(code: str, days: int):
        if code == 'bad':
            raise OhlcvFetchError('boom')
        if code == 'empty':
            return []  # 全行被护栏跳过 → 视为失败
        return _bars(3)

    with patch('src.stocks_ohlcv_pipeline.fetch_ohlcv', side_effect=fake_fetch):
        report = run_ohlcv_pipeline(tmp_path / 'ohlcv',
                                    codes=['ok1', 'bad', 'empty', 'ok2'])

    assert report.success_count == 2
    assert sorted(report.failed) == ['bad', 'empty']
    assert (tmp_path / 'ohlcv' / 'ok1.json').exists()
    assert not (tmp_path / 'ohlcv' / 'bad.json').exists()


def test_run_unexpected_exception_isolated(tmp_path: Path):
    def fake_fetch(code: str, days: int):
        raise RuntimeError('unexpected')

    with patch('src.stocks_ohlcv_pipeline.fetch_ohlcv', side_effect=fake_fetch):
        report = run_ohlcv_pipeline(tmp_path / 'ohlcv', codes=['x'])

    assert report.failed_count == 1 and not list((tmp_path / 'ohlcv').glob('*.json'))


def test_run_universe_from_fetch_fn(tmp_path: Path):
    with patch('src.stocks_ohlcv_pipeline._fetch_universe',
               return_value=['600519']), \
         patch('src.stocks_ohlcv_pipeline.fetch_ohlcv',
               side_effect=lambda code, days: _bars(3)):
        report = run_ohlcv_pipeline(tmp_path / 'ohlcv')

    assert report.success_count == 1
    assert (tmp_path / 'ohlcv' / '600519.json').exists()


# ---- CLI ----

def test_cli_backfill_defaults_to_single_worker(tmp_path: Path):
    calls: dict[str, object] = {}

    def fake_run(out_dir, days, max_workers, codes):
        calls['out_dir'] = out_dir
        calls['days'] = days
        calls['max_workers'] = max_workers
        calls['codes'] = codes
        from src.stocks_history_pipeline import BackfillReport
        return BackfillReport(success=['600519'])

    with patch('sys.argv', ['prog', '--data-root', str(tmp_path / 'data'),
                            '--backfill']), \
         patch('src.stocks_ohlcv_pipeline.run_ohlcv_pipeline', new=fake_run):
        main()

    assert calls['out_dir'] == tmp_path / 'data' / 'stocks' / 'ohlcv'
    assert calls['days'] == KEEP_DAYS
    assert calls['max_workers'] == 1  # backfill 防新浪限速
    assert calls['codes'] is None


def test_cli_increment_defaults_and_override(tmp_path: Path):
    workers: list[int] = []

    def fake_run(out_dir, days, max_workers, codes):
        workers.append(max_workers)
        from src.stocks_history_pipeline import BackfillReport
        return BackfillReport(success=['a'])

    with patch('sys.argv', ['prog', '--data-root', str(tmp_path)]), \
         patch('src.stocks_ohlcv_pipeline.run_ohlcv_pipeline', new=fake_run):
        main()  # 增量默认 4
    with patch('sys.argv', ['prog', '--data-root', str(tmp_path),
                            '--max-workers', '8', '--codes', '600519']), \
         patch('src.stocks_ohlcv_pipeline.run_ohlcv_pipeline', new=fake_run):
        main()  # 显式覆盖 + 指定 codes

    assert workers == [4, 8]


def test_cli_exits_loudly_when_all_fetches_fail(tmp_path: Path):
    with patch('sys.argv', ['prog', '--data-root', str(tmp_path)]), \
         patch('src.stocks_ohlcv_pipeline._fetch_universe',
               return_value=['600519', '000001']), \
         patch('src.stocks_ohlcv_pipeline.fetch_ohlcv',
               side_effect=OhlcvFetchError('down')), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1  # 数据源不可用 → 响亮失败防静默停更
