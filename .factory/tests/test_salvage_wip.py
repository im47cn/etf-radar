"""salvage_wip 真实逻辑回归（#14 补遗，#165 r1-r3 事故）——提取真实函数体执行。

事故背景：#165 r1-r3 implement 未提交即死（rev-list=0），EXIT trap 的
salvage push 无物可推，WIP 随 `worktree remove --force` 湮灭。salvage_wip
兜底未提交面：intent-to-add 使 untracked 入 diff，binary diff 快照到
ISSUE_DIR（下轮 implement 的证据输入，不自动续作）。

对齐 test_b1_fallback 的提取哲学：正则锚定函数名提取真实代码源化执行，
不复制逻辑——改 fix-issue.sh 不改本测试即红。

运行：python3 -m pytest .factory/tests -q
"""

import re
import subprocess
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]

_FUNC = re.search(
    r"\n(  salvage_wip\(\) \{.*?\n  \})\n",
    (FACTORY / "fix-issue.sh").read_text(encoding="utf-8"), re.S)
assert _FUNC is not None, "fix-issue.sh 缺 salvage_wip 函数体——锚定失效即红"
FUNC = _FUNC[1]
_DRIVER = r"""#!/usr/bin/env bash
set -euo pipefail
DIR="__DIR__"
WT="__WT__"
ROUND=3
__FUNC__
salvage_wip "$1"
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, dirty: bool) -> Path:
    """临时 git 仓 + 基线提交；dirty=True 时留未提交改动 + untracked。"""
    repo = tmp_path / "wt"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f1").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    if dirty:
        (repo / "f1").write_text("modified\n", encoding="utf-8")
        (repo / "f2").write_text("untracked\n", encoding="utf-8")
    return repo


def _run_salvage(tmp_path: Path, rc: str, dirty: bool):
    repo = _repo(tmp_path, dirty)
    issue_dir = tmp_path / "issue"
    issue_dir.mkdir()
    drv = tmp_path / "drv.sh"
    drv.write_text(_DRIVER
                   .replace("__DIR__", str(issue_dir))
                   .replace("__WT__", str(repo))
                   .replace("__FUNC__", FUNC), encoding="utf-8")
    r = subprocess.run(["/bin/bash", str(drv), rc], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr  # #23 纪律：best-effort 恒 return 0
    patch = issue_dir / "salvage-r3.patch"
    return patch.read_text(encoding="utf-8") if patch.exists() else None


def test_dirty_worktree_snapshots_tracked_and_untracked(tmp_path):
    """rc≠0 + 有未提交面：patch 含 tracked 修改与 untracked 新文件。"""
    patch = _run_salvage(tmp_path, "1", dirty=True)
    assert patch, "未提交 WIP 未落快照"
    assert "modified" in patch          # tracked 修改入快照
    assert "untracked" in patch and "new file" in patch  # -N 使 untracked 入 diff


def test_clean_worktree_leaves_no_patch(tmp_path):
    """rc≠0 但零改动：不留噪声 patch 文件。"""
    assert _run_salvage(tmp_path, "1", dirty=False) is None


def test_success_skips_snapshot(tmp_path):
    """rc=0（成功链）：不产 patch——成功路径产物在分支本身。"""
    assert _run_salvage(tmp_path, "0", dirty=True) is None
