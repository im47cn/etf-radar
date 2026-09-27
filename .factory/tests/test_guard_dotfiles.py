"""normalize 点前缀回归（2026-08-25 ADR-007 移植实测：lstrip("./") 使
点前缀周界整体失效——.factory/forge → factory/forge 绕过匹配）。"""
import importlib.util
from importlib.machinery import SourceFileLoader
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
_loader = SourceFileLoader("guard", str(HERE / "guard.py"))
_spec = importlib.util.spec_from_loader("guard", _loader)
guard = importlib.util.module_from_spec(_spec)
_loader.exec_module(guard)


def test_normalize_keeps_leading_dot():
    assert guard.normalize(".factory/forge") == ".factory/forge"
    assert guard.normalize(".gitignore") == ".gitignore"
    assert guard.normalize(".github/workflows/x.yml") == ".github/workflows/x.yml"


def test_normalize_strips_literal_dot_slash():
    assert guard.normalize("./src/A.java") == "src/A.java"
    assert guard.normalize("src\\A.java") == "src/A.java"
    assert guard.normalize("  src/A.java  ") == "src/A.java"


def test_violates_dotfile_perimeter():
    # PERIMETER 来自本仓 factory-local.json（含 .factory/、.github/、.gitignore）
    assert guard.violates(".factory/forge") == ".factory/"
    assert guard.violates(".gitignore") == ".gitignore"
    assert guard.violates(".github/workflows/ci.yml") == ".github/"
    assert guard.violates("src/A.java") is None
