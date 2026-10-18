"""BASE_BRANCH 两级解析（issue #133）——提取真实块在沙箱执行。

原固定回退 main 绕过 hosting.py 的 Codeup 拒猜不变量（master 仓静默落错
基线）。三态钉死：env 显式优先 / origin/HEAD 实际默认分支 / 两者皆无
fail-closed。与 trap 测试同哲学：不复制逻辑，正则提取真实块（改脚本不
改测试即红）。

解析块现有两份逐字拷贝（fix-issue.sh / upstream-sync-check.sh，后者为
#133 收口遗留补齐）——按脚本 parametrize 提取，钉住拷贝等价：任一侧
漂移（丢 2>/dev/null、改 sed）即红。
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from gitenv import git_env

FACTORY = Path(__file__).resolve().parents[1]

_SCRIPTS = ["fix-issue.sh", "upstream-sync-check.sh"]

_BLOCK_RE = re.compile(
    r'\n(BASE_BRANCH="\$\{FACTORY_BASE_BRANCH:-\}"[^\n]*\n.*?\[ -n "\$\{BASE_BRANCH\}" \] \|\|[^\n]*\n)', re.S)


def _block(script: str) -> str:
    return _BLOCK_RE.search(
        (FACTORY / script).read_text(encoding="utf-8"))[1]

_SANDBOX = r"""#!/usr/bin/env bash
set -euo pipefail
REPO="__REPO__"
__BLOCK__
echo "RESOLVED=${BASE_BRANCH}"
"""


def _env():
    env = git_env()
    env.pop("FACTORY_BASE_BRANCH", None)
    return env


def _run(repo: Path, script: str, extra_env=None):
    with tempfile.TemporaryDirectory() as sh_dir:
        sh = Path(sh_dir) / "sandbox.sh"
        sh.write_text(_SANDBOX.replace("__REPO__", str(repo))
                      .replace("__BLOCK__", _block(script)))
        env = _env()
        env.update(extra_env or {})
        return subprocess.run(["/bin/bash", str(sh)], env=env,
                              capture_output=True, text=True)


def _mk_clone(tmp: Path, default_branch: str) -> Path:
    """clone 自带提交的仓（默认分支可指定），origin/HEAD 由 clone 设置。"""
    seed = tmp / "seed"
    seed.mkdir()
    env = git_env()
    (seed / "README.md").write_text("# t\n", encoding="utf-8")
    for args in (("init", "-q", "-b", default_branch),
                 ("config", "user.email", "t@t"),
                 ("config", "user.name", "t"), ("add", "-A"),
                 ("commit", "-q", "-m", "init")):
        subprocess.run(["git", *args], cwd=seed, env=env, check=True,
                       capture_output=True)
    # 空 bare 仓 clone 不设 origin/HEAD（实测 fatal: not a symbolic ref），
    # 须经 --bare 带提交克隆后再 clone
    subprocess.run(["git", "clone", "-q", "--bare", str(seed),
                    str(tmp / "up.git")], env=env, check=True,
                   capture_output=True)
    subprocess.run(["git", "clone", "-q", str(tmp / "up.git"), str(tmp / "dn")],
                   env=env, check=True, capture_output=True)
    return tmp / "dn"


def test_blocks_are_identical():
    # 拷贝等价不变量显式钉死（Sourcery PR #256）：行为测试只钉三态语义，
    # 行为等价的文本漂移（如 sed 表达式微调）须靠逐字相等断言拦截
    assert _block("fix-issue.sh") == _block("upstream-sync-check.sh")


@pytest.mark.parametrize("script", _SCRIPTS)
def test_env_override_wins(tmp_path, script):
    dn = _mk_clone(tmp_path, "main")
    r = _run(dn, script, {"FACTORY_BASE_BRANCH": "custom-base"})
    assert r.returncode == 0
    assert "RESOLVED=custom-base" in r.stdout


@pytest.mark.parametrize("script", _SCRIPTS)
def test_origin_head_master_repo_resolves_master(tmp_path, script):
    """Codeup master 仓场景（#133 核心）：无 env 时读实际默认分支而非 main。"""
    dn = _mk_clone(tmp_path, "master")
    r = _run(dn, script)
    assert r.returncode == 0
    assert "RESOLVED=master" in r.stdout


@pytest.mark.parametrize("script", _SCRIPTS)
def test_no_origin_no_env_fail_closed(tmp_path, script):
    """裸仓（无 origin/HEAD）且无 env：拒猜基线 fail-closed（issue #133）。"""
    lone = tmp_path / "lone"
    lone.mkdir()
    env = git_env()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"),
                 ("config", "user.name", "t")):
        subprocess.run(["git", *args], cwd=lone, env=env, check=True,
                       capture_output=True)
    r = _run(lone, script)
    assert r.returncode == 2
    assert "issue #133" in r.stderr
