import json
import os
import tempfile
from pathlib import Path

import pytest

from src.output.writer import atomic_write_json


def test_atomic_write_creates_file_with_content() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'out.json'
        atomic_write_json(p, {'a': 1, 'b': '中文'})
        loaded = json.loads(p.read_text(encoding='utf-8'))
        assert loaded == {'a': 1, 'b': '中文'}


def test_atomic_write_creates_parent_dirs() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'nested' / 'sub' / 'out.json'
        atomic_write_json(p, {'x': 1})
        assert p.exists()


def test_atomic_write_preserves_old_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'out.json'
        atomic_write_json(p, {'old': True})

        # 模拟 os.replace 失败
        def fail(*a: object, **k: object) -> None:
            raise OSError('disk full')

        monkeypatch.setattr(os, 'replace', fail)
        try:
            atomic_write_json(p, {'new': True})
        except OSError:
            pass
        assert json.loads(p.read_text(encoding='utf-8')) == {'old': True}
