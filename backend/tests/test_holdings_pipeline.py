"""holdings_pipeline 主流程及辅助函数测试"""
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.holdings_pipeline import candidate_quarters, run_holdings_pipeline
from src.models import EtfHoldingsSnapshot, EtfTopHolding


def test_candidate_quarters_january():
    # Jan 15 2026 → 最近季末是 2025-12-31，候选回退到 2025-12/09/06/03
    out = candidate_quarters(date(2026, 1, 15))
    assert out == [date(2025, 12, 31), date(2025, 9, 30), date(2025, 6, 30), date(2025, 3, 31)]


def test_candidate_quarters_on_quarter_end():
    # 3 月 31 日当天 → 当季已结束，候选首位是 2026-03-31
    out = candidate_quarters(date(2026, 3, 31))
    assert out[0] == date(2026, 3, 31)
    assert out[1] == date(2025, 12, 31)


def test_candidate_quarters_mid_quarter():
    # 5 月 1 日 → 最近季末是 2026-03-31
    out = candidate_quarters(date(2026, 5, 1))
    assert out[0] == date(2026, 3, 31)


def test_candidate_quarters_returns_four():
    out = candidate_quarters(date(2026, 7, 15))
    assert len(out) == 4


def _make_snap(code: str, quarter: date) -> EtfHoldingsSnapshot:
    return EtfHoldingsSnapshot(
        etf_code=code,
        etf_name=f'{code}-name',
        disclosure_date=quarter,
        fetched_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        top_holdings=[EtfTopHolding(code='002129', name='TCL中环', weight=8.5)],
    )


def test_run_holdings_pipeline_writes_json(tmp_path: Path):
    themes_yaml = tmp_path / 'themes.yml'
    themes_yaml.write_text(
        'themes:\n'
        '  - id: semiconductor\n'
        '    name: 半导体\n'
        '    us_etfs: [SOXX]\n'
        '    primary_us: SOXX\n'
        '    primary_cn: "512480"\n'
        '    cn_etfs:\n'
        '      - code: "512480"\n'
        '        name: 半导体ETF\n'
        '        tracking: 中证全指半导体\n'
        '        match_type: exact\n',
        encoding='utf-8',
    )
    out_dir = tmp_path / 'holdings'

    def fake_fetch(self, etf_code, etf_name, quarter):
        return _make_snap(etf_code, quarter)

    with patch('src.holdings_pipeline.HoldingsProvider.fetch', new=fake_fetch):
        report = run_holdings_pipeline(
            themes_yaml=themes_yaml,
            output_dir=out_dir,
            today=date(2026, 6, 23),
        )

    assert report.success == ['512480']
    snap_path = out_dir / '512480.json'
    assert snap_path.exists()
    data = json.loads(snap_path.read_text())
    assert data['etf_code'] == '512480'
    assert data['disclosure_date'] == '2026-03-31'


def test_run_holdings_pipeline_quarter_fallback(tmp_path: Path):
    themes_yaml = tmp_path / 'themes.yml'
    themes_yaml.write_text(
        'themes:\n'
        '  - id: x\n    name: X\n    us_etfs: []\n    primary_cn: "512480"\n'
        '    cn_etfs:\n      - code: "512480"\n        name: x\n'
        '        tracking: x\n        match_type: exact\n',
        encoding='utf-8',
    )

    calls = []

    def fake_fetch(self, etf_code, etf_name, quarter):
        calls.append(quarter)
        if quarter == date(2026, 3, 31):
            from src.providers.holdings_provider import HoldingsFetchError
            raise HoldingsFetchError('empty')
        return _make_snap(etf_code, quarter)

    with patch('src.holdings_pipeline.HoldingsProvider.fetch', new=fake_fetch):
        report = run_holdings_pipeline(
            themes_yaml=themes_yaml,
            output_dir=tmp_path / 'h',
            today=date(2026, 6, 23),
        )
    assert calls[0] == date(2026, 3, 31)
    assert calls[1] == date(2025, 12, 31)
    assert report.success == ['512480']


def test_run_holdings_pipeline_single_etf_failure_isolated(tmp_path: Path):
    themes_yaml = tmp_path / 'themes.yml'
    themes_yaml.write_text(
        'themes:\n'
        '  - id: a\n    name: A\n    us_etfs: []\n    primary_cn: "512480"\n'
        '    cn_etfs:\n      - code: "512480"\n        name: x\n'
        '        tracking: x\n        match_type: exact\n'
        '  - id: b\n    name: B\n    us_etfs: []\n    primary_cn: "159870"\n'
        '    cn_etfs:\n      - code: "159870"\n        name: y\n'
        '        tracking: y\n        match_type: exact\n',
        encoding='utf-8',
    )

    def fake_fetch(self, etf_code, etf_name, quarter):
        from src.providers.holdings_provider import HoldingsFetchError
        if etf_code == '512480':
            raise HoldingsFetchError('boom')
        return _make_snap(etf_code, quarter)

    with patch('src.holdings_pipeline.HoldingsProvider.fetch', new=fake_fetch):
        report = run_holdings_pipeline(
            themes_yaml=themes_yaml,
            output_dir=tmp_path / 'h',
            today=date(2026, 6, 23),
        )
    assert report.success == ['159870']
    assert report.failed == ['512480']
