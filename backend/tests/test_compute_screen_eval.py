"""compute_screen_eval 端到端: 固定 snapshots + 固定 ohlcv → 固定事件计数/结构/超额."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.compute_screen_eval import benchmark_returns, compute_screen_eval, main


def _dates(start: str, n: int) -> list[str]:
    d = datetime.strptime(start, '%Y-%m-%d').date()  # noqa: DTZ007  仅产日期串, 无时区语义
    out: list[str] = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(dates: list[str], closes: list[float]) -> list[dict[str, Any]]:
    return [{'d': d, 'o': c, 'h': c, 'l': c, 'c': c, 'v': 1, 'amt': 1}
            for d, c in zip(dates, closes)]


def _write_trading(data_root: Path, d: str, cands: list[dict[str, Any]]) -> None:
    p = data_root / 'snapshots' / d
    p.mkdir(parents=True, exist_ok=True)
    (p / 'trading.json').write_text(json.dumps({'candidates': cands}), encoding='utf-8')


def _write_ohlcv(data_root: Path, code: str, bars: list[dict[str, Any]]) -> None:
    p = data_root / 'stocks' / 'ohlcv' / f'{code}.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({'schema_version': '1.0', 'code': code, 'bars': bars}),
                 encoding='utf-8')


_CAND_A = {'code': '601001', 'pivot': 10.0, 'stop': 9.0, 'composite_score': 5.5,
           'rs_pct': 79.6, 'vcp': {'quality': 0.7}, 'state': 'watch'}
_CAND_B = {'code': '601002', 'pivot': 10.0, 'stop': 9.5, 'composite_score': 4.0,
           'rs_pct': 65.0, 'vcp': {'quality': 0.4}, 'state': 'in_buy_zone'}
_CAND_C = {'code': '601003', 'pivot': 8.0, 'stop': 7.5, 'composite_score': 3.0,
           'rs_pct': 55.0, 'vcp': {'quality': 0.2}, 'state': 'watch'}


def _seed_tree(tmp_path: Path) -> list[str]:
    """固定数据树: 2 个快照 (A/B 入池 01-05, 01-06 重复 A/B 再增 C) + 3 份行情 + 基准."""
    _write_trading(tmp_path, '2026-01-05', [_CAND_A, _CAND_B])
    _write_trading(tmp_path, '2026-01-06', [_CAND_A, _CAND_B, _CAND_C])
    # A: case A 常规突破 (第 5 根 10.6 突破, T+20 exit 13.0 → r=1.5)
    dates_a = _dates('2026-01-05', 26)
    closes_a = [9.8, 9.7, 9.75, 9.8, 9.85, 10.6] + [round(10.6 + 0.12 * (k - 5), 2)
                                                    for k in range(6, 26)]
    _write_ohlcv(tmp_path, '601001', _bars(dates_a, closes_a))
    # B: 入池即 in_buy_zone (entry=10.2, T+20 exit 12.2 → r=(12.2-10.2)/(10.2-9.5)=2.8571)
    dates_b = _dates('2026-01-05', 21)
    closes_b = [round(10.2 + 0.1 * k, 2) for k in range(21)]
    _write_ohlcv(tmp_path, '601002', _bars(dates_b, closes_b))
    # C: 无 ohlcv 文件 → missing_quotes
    # 基准 000985: 40 根平价 bar → 同窗口基准收益恒 0 → excess == ret
    bench_dates = _dates('2026-01-05', 40)
    _write_ohlcv(tmp_path, '000985', _bars(bench_dates, [100.0] * 40))
    return bench_dates


def test_compute_screen_eval_fixed_events(tmp_path: Path) -> None:
    _seed_tree(tmp_path)

    result = compute_screen_eval(tmp_path)

    assert result['schema_version'] == '1.0'
    assert result['as_of_date'] == '2026-01-06'
    assert result['sample'] == {'first_pool_date': '2026-01-05', 'last_pool_date': '2026-01-06',
                                'n_snapshots': 2, 'n_candidates': 3}  # A/B 重复出现被去重
    assert result['events'] == {'total': 3, 'broke_out': 2, 'never_broke_out': 0,
                                'pending': 0, 'missing_quotes': 1,
                                'breakout_rate': 1.0, 'breakout_rate_status': 'insufficient'}
    # 基准: 文件存在 → ok; as_of = 基准末根日期
    assert result['benchmark'] == {'code': '000985', 'status': 'ok',
                                   'as_of': _dates('2026-01-05', 40)[-1]}
    # returns: 两个有效事件 r=[1.5, 2.8571] 全正 → hit_rate=1 (n=2<50 → insufficient)
    returns = result['returns']
    assert returns['n'] == 2 and returns['hit_rate'] == 1.0
    assert returns['status'] == 'insufficient'
    assert returns['median_r'] == pytest.approx(2.1786, abs=1e-4)
    # 基准平价 → excess == ret; T+5: [0.0566, 0.049], T+20: [0.2264, 0.1961]
    by_t = {row['horizon']: row for row in result['by_t']}
    assert by_t[5]['n'] == 2 and by_t[5]['mean_ret'] == pytest.approx(0.0528, abs=1e-4)
    assert by_t[5]['median_excess'] == pytest.approx(0.0528, abs=1e-4)
    assert by_t[20]['n'] == 2 and by_t[20]['mean_ret'] == pytest.approx(0.2113, abs=1e-4)
    assert result['returns']['median_excess_20d'] == pytest.approx(0.2113, abs=1e-4)
    # 分档: 3 维度 9 行全输出
    assert len(result['buckets']) == 9


def test_compute_screen_eval_empty_root(tmp_path: Path) -> None:
    """空数据根 (无任何 trading.json 快照): 首批 0 事件, 输出结构仍完整."""
    result = compute_screen_eval(tmp_path)

    assert result['events']['total'] == 0
    assert result['events']['broke_out'] == 0
    assert result['events']['breakout_rate'] == 0.0
    assert result['events']['breakout_rate_status'] == 'insufficient'
    assert result['as_of_date'] is None
    assert result['sample'] == {'first_pool_date': None, 'last_pool_date': None,
                                'n_snapshots': 0, 'n_candidates': 0}
    assert result['benchmark']['status'] == 'unavailable'
    assert result['benchmark']['as_of'] is None
    assert result['returns']['n'] == 0 and result['returns']['status'] == 'insufficient'
    assert result['returns']['median_excess_20d'] is None
    assert len(result['buckets']) == 9
    assert all(row['n'] == 0 for row in result['buckets'])


def test_main_writes_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_tree(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['compute_screen_eval', '--data-root', str(tmp_path)])

    main()

    out = tmp_path / 'latest' / 'screen_eval.json'
    assert out.exists()
    doc = json.loads(out.read_text(encoding='utf-8'))
    assert doc['schema_version'] == '1.0'
    assert doc['events']['total'] == 3


def test_benchmark_returns_alignment() -> None:
    """基准对齐: 定位首个 d>=event_date; 事件日晚于基准末根或 +n 越界 → None."""
    dates = _dates('2026-01-05', 10)
    bench = _bars(dates, [100.0] * 9 + [110.0])  # 末根 +10%

    assert benchmark_returns(bench, '2026-01-05', 1) == 0.0       # 首根对齐, 次根平价
    assert benchmark_returns(bench, '2026-01-06', 8) == pytest.approx(0.1)  # 末根 110/100-1
    assert benchmark_returns(bench, '2026-01-07', 0) == 0.0       # n=0 对齐日自身
    assert benchmark_returns(bench, '2026-01-07', 9) is None      # k+n 越界
    assert benchmark_returns(bench, '2099-01-01', 1) is None      # 事件日晚于基准末根
    assert benchmark_returns([], '2026-01-05', 1) is None         # 空基准序列
