"""fresh-clone 容错回归：gitignored 周界路径缺失不误拦，非忽略缺失仍拦。

对应修复：guard.self_check 存在性三态——gitignored 豁免（fresh clone 检不出
且无主树可回退）、非忽略缺失拦截（M-02「从未存在」防线保持）。
夹具为独立临时 git 仓：self_check 依赖 rev-parse/check-ignore，须真实 .git。
"""
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import shutil
import subprocess
from pathlib import Path

import pytest

GUARD_SRC = Path(__file__).resolve().parent.parent / "guard.py"
# .localcfg/ 写入 .gitignore 且不创建——模拟 fresh clone 检不出本机配置目录
PERIMETER = ["MISSION.md", "docs/", ".localcfg/"]


def _build_repo(tmp_path: Path, perimeter: list) -> Path:
    root = tmp_path / "repo"
    fac = root / ".factory"
    fac.mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs" / "note.md").write_text("x", encoding="utf-8")
    shutil.copyfile(GUARD_SRC, fac / "guard.py")
    (fac / "factory-local.json").write_text(
        json.dumps({"perimeter": perimeter}), encoding="utf-8")
    lines = "\n".join(f"- `{p}`" for p in perimeter)
    (root / "MISSION.md").write_text(
        f"# 任务\n\n## 周界（PERIMETER）\n\n{lines}\n", encoding="utf-8")
    (root / ".gitignore").write_text(".localcfg/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def _load_guard(root: Path):
    loader = SourceFileLoader(
        "factory_guard_fresh_clone", str(root / ".factory" / "guard.py"))
    spec = importlib.util.spec_from_loader("factory_guard_fresh_clone", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_gitignored_absent_passes_on_fresh_clone(tmp_path):
    """.localcfg/ 缺失且 gitignored → self_check 通过（fresh clone 正常态）。"""
    mod = _load_guard(_build_repo(tmp_path, PERIMETER))
    mod.self_check()


def test_absent_non_ignored_still_blocked(tmp_path):
    """vanished/ 缺失且非 ignored → 拦截（M-02 从未存在防线不变）。"""
    mod = _load_guard(_build_repo(tmp_path, PERIMETER + ["vanished/"]))
    with pytest.raises(RuntimeError, match="周界路径不存在"):
        mod.self_check()


def test_rev_parse_failure_fails_closed(tmp_path):
    """CodeRabbit xx-skills#14：REPO_ROOT 非 git 仓（rev-parse 失败）时
    main_root 不得退化为空串相对 CWD 解析（fail-open）——git 不可用走
    check-ignore fail-closed（与下方 git 异常立场一致），不静默放行。"""
    root = _build_repo(tmp_path, PERIMETER)  # .localcfg/ 缺失非 ignored 检查路径
    subprocess.run(["rm", "-rf", str(root / ".git")], check=True)
    mod = _load_guard(root)
    with pytest.raises(RuntimeError, match="git check-ignore"):
        mod.self_check()


def test_rev_parse_failure_cwd_lookalike_still_fails_closed(tmp_path, monkeypatch):
    """CodeRabbit #119：rev-parse 失败且 CWD 恰含同名周界路径时，
    main_root 为 "" 会令 Path("")/p 相对 CWD 解析、exists() 误真而放行
    （fail-open）——None 语义禁掉主树回退，check-ignore 照常 fail-closed。
    此场景击杀旧实现（空串哨兵放行），本实现必须仍抛。"""
    root = _build_repo(tmp_path, PERIMETER)  # REPO_ROOT 缺 .localcfg/
    lookalike = tmp_path / "lookalike"
    lookalike.mkdir()
    (lookalike / ".localcfg").mkdir()
    monkeypatch.chdir(lookalike)  # CWD 含同名路径：旧实现误判存在
    subprocess.run(["rm", "-rf", str(root / ".git")], check=True)
    mod = _load_guard(root)
    with pytest.raises(RuntimeError, match="git check-ignore"):
        mod.self_check()
