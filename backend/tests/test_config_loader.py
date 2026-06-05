from pathlib import Path
import pytest
from src.config_loader import load_themes, load_algo_config

FIXT = Path(__file__).parent / 'fixtures'


def test_load_themes_returns_list() -> None:
    themes = load_themes(FIXT / 'themes_minimal.yml')
    assert len(themes) == 1
    assert themes[0].id == 't1'


def test_load_algo_config() -> None:
    cfg = load_algo_config(FIXT / 'algo_minimal.yml')
    assert cfg.strength.k_sigmoid == 5.0
    assert cfg.confidence.exact == 90


def test_load_themes_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_themes(FIXT / 'nope.yml')


def test_real_themes_yml_has_14() -> None:
    real = Path(__file__).parent.parent.parent / 'config' / 'themes.yml'
    themes = load_themes(real)
    assert len(themes) == 14
