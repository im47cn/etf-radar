from pathlib import Path
import pytest
from src.config_loader import load_themes, load_algo_config

FIXT = Path(__file__).parent / 'fixtures'


def test_load_themes_returns_list() -> None:
    themes = load_themes(FIXT / 'themes_minimal.yml')
    assert len(themes) >= 1
    assert themes[0].id == 't1'


def test_load_algo_config() -> None:
    cfg = load_algo_config(FIXT / 'algo_minimal.yml')
    assert cfg.strength.k_sigmoid == 5.0
    assert cfg.confidence.exact == 90


def test_load_themes_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_themes(FIXT / 'nope.yml')


def test_real_themes_yml_count() -> None:
    real = Path(__file__).parent.parent.parent / 'config' / 'themes.yml'
    themes = load_themes(real)
    # 12 mapped + 15 CN-only (7 独立行业 + 半导体设备/科创100 + 拆分: 券商/煤炭/银行/有色/电池/油气)
    assert len(themes) == 27


def test_load_themes_includes_cn_only_count():
    real = Path(__file__).parent.parent.parent / 'config' / 'themes.yml'
    themes = load_themes(real)
    cn_only = [t for t in themes if t.primary_us is None]
    assert len(cn_only) >= 7, f"expected >=7 cn_only themes, got {len(cn_only)}"
    expected_ids = {
        'cn_liquor', 'cn_consumer_staples', 'cn_medical_devices',
        'cn_home_appliances', 'cn_real_estate', 'cn_media', 'cn_dividend',
    }
    actual = {t.id for t in cn_only}
    assert expected_ids.issubset(actual), f"missing: {expected_ids - actual}"


def test_load_themes_cn_only_have_primary_cn():
    real = Path(__file__).parent.parent.parent / 'config' / 'themes.yml'
    themes = load_themes(real)
    for t in themes:
        if t.primary_us is None:
            assert t.primary_cn is not None, f"{t.id} missing primary_cn"
            assert any(cn.code == t.primary_cn for cn in t.cn_etfs), \
                f"{t.id}: primary_cn {t.primary_cn} not in cn_etfs"
