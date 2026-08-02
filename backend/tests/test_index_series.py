"""index_series 管线测试: 重对齐 / 缺口填 null / 单指数失败不阻断."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.market_breadth.index_series import INDICES, _align, build_index_series, run
from src.providers.index_provider import IndexCloseProvider


class FakeProvider:
    """伪指数数据源, 满足 IndexCloseProvider Protocol."""

    def __init__(
        self,
        data: dict[str, list[tuple[date, float]]] | None = None,
        fail: set[str] | None = None,
    ) -> None:
        self.data = data or {}
        self.fail = fail or set()

    def fetch_close(self, code: str) -> list[tuple[date, float]]:
        if code in self.fail:
            raise RuntimeError(f'{code} boom')
        return self.data.get(code, [])


# 静态类型断言: FakeProvider 满足 Protocol (否则 mypy strict 报错)
_proto_check: IndexCloseProvider = FakeProvider()


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


def test_build_index_series_single_failure_does_not_abort() -> None:
    dates = ['2026-01-01', '2026-01-02']
    provider = FakeProvider(
        data={
            '000001': [(date(2026, 1, 1), 3000.0), (date(2026, 1, 2), 3010.0)],
        },
        fail={'399001'},
    )
    snapshot = build_index_series(
        dates, provider, indices=[('000001', '上证指数'), ('399001', '深证成指')]
    )

    assert snapshot['schema_version'] == '1.0'
    assert snapshot['dates'] == dates
    by_code = {idx['code']: idx for idx in snapshot['indices']}
    assert by_code['000001']['series'] == [3000.0, 3010.0]
    # 失败指数 series 全 null, 但仍保留在输出中
    assert by_code['399001']['series'] == [None, None]
    assert by_code['399001']['name'] == '深证成指'


def test_build_index_series_uses_default_indices_constant() -> None:
    snapshot = build_index_series(['2026-01-01'], FakeProvider())
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
    provider = FakeProvider(data={'000001': [(date(2026, 1, 1), 3000.5)]})

    out = run(tmp_path, provider=provider)
    data = json.loads(out.read_text(encoding='utf-8'))
    assert out == latest / 'index_series.json'
    assert data['dates'] == ['2026-01-01', '2026-01-02']
    sh = {idx['code']: idx['series'] for idx in data['indices']}['000001']
    assert sh == [3000.5, None]
