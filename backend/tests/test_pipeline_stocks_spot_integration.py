"""验证 run_pipeline 在 latest/ 下生成 stocks_spot.json"""
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.pipeline import run_pipeline, PipelineMode


@pytest.fixture
def fake_pipeline_env(tmp_path: Path):
    """搭建最小可运行环境：themes.yml + algo.yml + holdings dir。"""
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
    # 复用真实 algo.yml（使用绝对路径，兼容任意 cwd）
    real_algo = (Path(__file__).parents[2] / 'config' / 'algo.yml').read_text(encoding='utf-8')
    (config_dir / 'algo.yml').write_text(real_algo, encoding='utf-8')

    data_root = tmp_path / 'data'
    (data_root / 'latest').mkdir(parents=True)
    (data_root / 'holdings').mkdir(parents=True)
    (data_root / 'holdings' / '512480.json').write_text(json.dumps({
        'etf_code': '512480', 'etf_name': 'x',
        'disclosure_date': '2026-03-31', 'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'TCL中环', 'weight': 8.5}],
    }), encoding='utf-8')
    return config_dir, data_root


def test_run_pipeline_writes_stocks_spot(fake_pipeline_env):
    config_dir, data_root = fake_pipeline_env

    fake_spot = pd.DataFrame({
        '代码': ['002129'], '名称': ['TCL中环'],
        '最新价': [12.5], '涨跌幅': [2.5],
    })

    # 整体 mock 所有外部 provider，仅验证 stocks_spot 写入路径
    with patch('src.pipeline.YfinanceProvider'), \
         patch('src.pipeline.AkshareEmProvider'), \
         patch('src.pipeline.AkshareSinaProvider'), \
         patch('src.pipeline._collect_us_ohlc', return_value=({}, [])), \
         patch('src.pipeline._collect_cn_ohlc', return_value=({}, {}, [])), \
         patch('src.providers.stock_spot_provider.ak.stock_zh_a_spot_em',
               return_value=fake_spot):
        run_pipeline(
            mode=PipelineMode.FULL,
            data_root=data_root,
            config_dir=config_dir,
        )

    out = data_root / 'latest' / 'stocks_spot.json'
    assert out.exists()
    data = json.loads(out.read_text())
    assert '002129' in data['stocks']
