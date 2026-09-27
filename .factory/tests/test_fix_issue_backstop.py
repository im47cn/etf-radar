"""fix-issue.sh 5.5 未提交改动机械收编兜底——提取真实块载荷在真 git 沙箱执行。

issue #63 实证缺口：gate/holdout 验证工作区、push 只发 HEAD，review 修复
以工作区态存在即随 worktree 清理丢失。本块是脚本侧兜底（节点侧纪律见
prompts/review.md），三态钉死：脏树收编 / 净树零动作 / 提交被拒 fail-closed。
"""


import re
import subprocess
import tempfile
from pathlib import Path

from gitenv import git_env

FACTORY = Path(__file__).resolve().parents[1]

# 与 trap 测试同哲学：不复制逻辑，正则提取真实块（改脚本不改测试即红）
_BACKSTOP = re.search(
    r'\n(if \[ "\$\{DRY\}" = 0 \] && \[ -n "\$\(git -C "\$\{WT\}" '
    r'status --porcelain\)" \]; then\n.*?\nfi)\n',
    (FACTORY / "fix-issue.sh").read_text(encoding="utf-8"),
    re.S,
)[1]

SANDBOX = r"""#!/usr/bin/env bash
WT="__WT__"
DRY=0
__PAYLOAD__
"""


def _mk_repo(tmp: Path) -> Path:
    """单提交净仓（user 身份仓内配置，commit 无需 -c 注入）。"""
    wt = tmp / "wt"
    wt.mkdir()
    (wt / "README.md").write_text("# t\n", encoding="utf-8")
    env = git_env()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"),
                 ("config", "user.name", "t"), ("add", "-A"),
                 ("commit", "-q", "-m", "init")):
        subprocess.run(["git", *args], cwd=wt, env=env, check=True,
                       capture_output=True)
    return wt


def _run_block(wt: Path) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as sh_dir:
        sh = Path(sh_dir) / "sandbox.sh"
        sh.write_text(SANDBOX.replace("__WT__", str(wt)).replace("__PAYLOAD__", _BACKSTOP))
        return subprocess.run(["/bin/bash", str(sh)], env=git_env(),
                              capture_output=True, text=True)


def _git(wt: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=wt, env=git_env(),
                          check=True, capture_output=True, text=True).stdout


def test_backstop_commits_dirty_tree():
    """脏树（含未跟踪文件）→ 全量收编为单提交，树净。"""
    with tempfile.TemporaryDirectory() as tmp:
        wt = _mk_repo(Path(tmp))
        (wt / "fix.py").write_text("x = 1\n", encoding="utf-8")          # 已跟踪改动
        (wt / "new.md").write_text("n\n", encoding="utf-8")             # 未跟踪文件
        proc = _run_block(wt)
        assert proc.returncode == 0, proc.stderr
        assert "机械收编" in _git(wt, "log", "-1", "--format=%s")
        assert _git(wt, "status", "--porcelain") == ""                  # 收编后净
        assert "fix.py" in _git(wt, "show", "--name-only", "--format=")
        assert "new.md" in _git(wt, "show", "--name-only", "--format=")


def test_backstop_noop_on_clean_tree():
    """净树 → 零动作（HEAD 不动，不产生空提交）。"""
    with tempfile.TemporaryDirectory() as tmp:
        wt = _mk_repo(Path(tmp))
        before = _git(wt, "rev-parse", "HEAD")
        assert _run_block(wt).returncode == 0
        assert _git(wt, "rev-parse", "HEAD") == before


def test_backstop_fails_closed_when_commit_rejected():
    """commit 被钩子拒绝 → 块 exit 1（链终止，不静默丢改动）。"""
    with tempfile.TemporaryDirectory() as tmp:
        wt = _mk_repo(Path(tmp))
        hooks = Path(tmp) / "hooks"
        hooks.mkdir()
        (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (hooks / "pre-commit").chmod(0o755)
        _git(wt, "config", "core.hooksPath", str(hooks))
        (wt / "fix.py").write_text("x = 2\n", encoding="utf-8")
        proc = _run_block(wt)
        assert proc.returncode != 0
        assert "backstop 提交失败" in proc.stderr
