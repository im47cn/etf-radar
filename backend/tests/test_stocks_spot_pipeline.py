"""验证 stocks_spot 独立 pipeline 入口能产出 stocks_spot.json。"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.stocks_spot_pipeline import main


@pytest.fixture
def fake_holdings(tmp_path: Path) -> Path:
    """搭建最小 holdings 目录，含一个 ETF 季报快照。"""
    data_root = tmp_path / 'data'
    (data_root / 'latest').mkdir(parents=True)
    (data_root / 'holdings').mkdir(parents=True)
    (data_root / 'holdings' / '512480.json').write_text(json.dumps({
        'etf_code': '512480', 'etf_name': 'x',
        'disclosure_date': '2026-03-31', 'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'TCL中环', 'weight': 8.5}],
    }), encoding='utf-8')
    return data_root


def test_stocks_spot_pipeline_writes_snapshot(fake_holdings: Path, monkeypatch) -> None:
    data_root = fake_holdings
    fake_spot = pd.DataFrame({
        '代码': ['002129'], '名称': ['TCL中环'],
        '最新价': [12.5], '涨跌幅': [2.5],
    })

    monkeypatch.setattr(sys, 'argv',
                        ['stocks_spot_pipeline', f'--data-root={data_root}'])
    with patch('src.providers.stock_spot_provider.ak.stock_zh_a_spot_em',
               return_value=fake_spot):
        main()

    out = data_root / 'latest' / 'stocks_spot.json'
    assert out.exists()
    data = json.loads(out.read_text())
    assert '002129' in data['stocks']
    assert data['stocks']['002129']['close'] == 12.5
    assert data['stocks']['002129']['r_1d'] == pytest.approx(0.025)


def test_main_pipeline_does_not_write_stocks_spot(tmp_path: Path) -> None:
    """回归保护：主 pipeline 不再写 stocks_spot.json（已解耦）。"""
    from src.pipeline import run_pipeline, PipelineMode

    config_dir = tmp_path / 'config'
    config_dir.mkdir()
    (config_dir / 'themes.yml').write_text(
        'themes:\n'
        '  - id: x\n    name: X\n    us_etfs: [SOXX]\n    primary_us: SOXX\n'
        '    primary_cn: "512480"\n'
        '    cn_etfs:\n      - code: "512480"\n        name: x\n'
        '        tracking: x\n        match_type: exact\n',
        encoding='utf-8',
    )
    real_algo = (Path(__file__).parents[2] / 'config' / 'algo.yml').read_text(encoding='utf-8')
    (config_dir / 'algo.yml').write_text(real_algo, encoding='utf-8')

    data_root = tmp_path / 'data'
    (data_root / 'latest').mkdir(parents=True)
    (data_root / 'holdings').mkdir(parents=True)

    with patch('src.pipeline.YfinanceProvider'), \
         patch('src.pipeline.AkshareEmProvider'), \
         patch('src.pipeline.AkshareSinaProvider'), \
         patch('src.pipeline._collect_us_ohlc', return_value=({}, [])), \
         patch('src.pipeline._collect_cn_ohlc', return_value=({}, {}, [])):
        run_pipeline(
            mode=PipelineMode.FULL,
            data_root=data_root,
            config_dir=config_dir,
        )

    assert not (data_root / 'latest' / 'stocks_spot.json').exists(), \
        '主 pipeline 不应再写 stocks_spot.json'
