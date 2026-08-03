"""index_series 管线测试: 重对齐 / chain 逐级兜底 / 全源失败不阻断 / 温度缺失防御."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.market_breadth.index_series import INDICES, _align, build_index_series, run


class FakeProvider:
    """伪指数数据源, 满足 IndexCloseProvider Protocol."""

    def __init__(
        self,
        name: str,
        data: dict[str, list[tuple[date, float]]] | None = None,
        fail: set[str] | None = None,
    ) -> None:
        self.name = name
        self.data = data or {}
        self.fail = fail or set()

    def fetch_close(self, code: str) -> list[tuple[date, float]]:
        if code in self.fail:
            raise RuntimeError(f'{code} boom')
        return self.data.get(code, [])


def test_align_fills_missing_dates_with_none() -> None:
    dates = ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04']
    raw = [
        (date(2026, 1, 1), 100.0),
        (date(2026, 1, 3), 102.0),
        (date(2026, 1, 9), 999.0),  # 温度图外, 应忽略
    ]
    assert _align(dates, raw) == [100.0, None, 102.0, None]


def test_align_empty_raw_yields_all_none() -> None:
    dates = ['2026-01-01', '2026-01-02']
    assert _align(dates, []) == [None, None]


def test_chain_falls_back_to_second_provider_when_primary_fails() -> None:
    """首选源抛错 → chain 自动切到兜底源."""
    dates = ['2026-01-01', '2026-01-02']
    primary = FakeProvider(name='primary', fail={'000001'})
    fallback = FakeProvider(
        name='fallback',
        data={'000001': [(date(2026, 1, 1), 3000.0), (date(2026, 1, 2), 3010.0)]},
    )
    snapshot = build_index_series(
        dates, [primary, fallback], indices=[('000001', '上证指数')]
    )
    sh = {idx['code']: idx for idx in snapshot['indices']}['000001']
    assert sh['series'] == [3000.0, 3010.0]


def test_chain_all_providers_fail_yields_null_series_without_raising() -> None:
    dates = ['2026-01-01', '2026-01-02']
    providers = [
        FakeProvider(name='p1', fail={'000001'}),
        FakeProvider(name='p2', fail={'000001'}),
    ]
    snapshot = build_index_series(
        dates, providers, indices=[('000001', '上证指数'), ('399001', '深证成指')],
    )
    by_code = {idx['code']: idx for idx in snapshot['indices']}
    # 000001 两源全失败 → 全 null
    assert by_code['000001']['series'] == [None, None]
    # 399001 两源都返回空 (data 里无该 code) → 也全 null, 但仍保留在输出中
    assert by_code['399001']['series'] == [None, None]
    assert by_code['399001']['name'] == '深证成指'


def test_build_index_series_uses_default_indices_constant() -> None:
    snapshot = build_index_series(['2026-01-01'], [FakeProvider(name='p')])
    codes = [idx['code'] for idx in snapshot['indices']]
    assert codes == [c for c, _ in INDICES]
    assert len(codes) == 6


def test_run_reads_temperature_dates_and_writes_json(tmp_path: Path) -> None:
    latest = tmp_path / 'latest'
    latest.mkdir()
    (latest / 'market_temperature.json').write_text(
        json.dumps({'dates': ['2026-01-01', '2026-01-02'], 'schema_version': '2.0'}),
        encoding='utf-8',
    )
    provider = FakeProvider(name='p', data={'000001': [(date(2026, 1, 1), 3000.5)]})

    out = run(tmp_path, providers=[provider])
    data = json.loads(out.read_text(encoding='utf-8'))
    assert out == latest / 'index_series.json'
    assert data['dates'] == ['2026-01-01', '2026-01-02']
    sh = {idx['code']: idx['series'] for idx in data['indices']}['000001']
    assert sh == [3000.5, None]


def test_run_writes_empty_snapshot_when_temperature_missing(tmp_path: Path) -> None:
    """温度文件不存在时写空 index_series.json, 不抛错 (cron 韧性)."""
    latest = tmp_path / 'latest'
    latest.mkdir()
    out = run(tmp_path, providers=[FakeProvider(name='p')])
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['dates'] == []
    assert len(data['indices']) == 6
    assert all(idx['series'] == [] for idx in data['indices'])
