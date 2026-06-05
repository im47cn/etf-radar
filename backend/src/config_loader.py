"""加载 themes.yml 与 algo.yml"""
from pathlib import Path
from typing import Any

import yaml

from .models import AlgoConfig, ThemeConfig


def load_themes(path: Path | str) -> list[ThemeConfig]:
    p = Path(path)
    with p.open(encoding='utf-8') as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return [ThemeConfig(**t) for t in data['themes']]


def load_algo_config(path: Path | str) -> AlgoConfig:
    p = Path(path)
    with p.open(encoding='utf-8') as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return AlgoConfig(**data)
