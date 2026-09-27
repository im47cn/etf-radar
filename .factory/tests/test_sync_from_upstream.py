"""sync-from-upstream.sh 回归测试 —— 补齐缺失文件分支（脚本首测）。

缺陷→测试映射:
- 缺失父目录写入崩溃（xx-skills 2026-08-31 事故：tests/ 目录整缺，
  「本地缺失」补齐分支对不存在路径直接重定向 → No such file or directory，
  apply 中途崩、锚点未写）→ TestApplyMissingParentDir：mkdir -p 补齐
  + blob 落地 + mode 恢复 + 锚点写入 + rc=0
- 退出码契约（头注释：0=干净/已同步 1=有漂移 2=用法/上游不可用）
  → TestCheckMissingFile：--check 对本地缺失 full 文件 rc=1
- 中心驱动契约（--repo 自任意 cwd 操作目标仓；目标非 git 仓 fail-closed）
  → TestRepoMode：产物落目标仓 + lock 含 upstream 字段 + 非 git/缺路径 rc=2
- --commit 契约（单提交落库 + blame-ignore 滞后一条 + 脏守卫 + 空追平
  不提交——防无漂移重跑链式生成噪音提交）→ TestApplyCommit
- PR #106 审查回归（--repo 子目录规范化到仓根，防 FACTORY/锁/分发错位；
  旧锁缺 upstream 字段的空追平须回填）→ TestPR106ReviewRegressions
- 字节码密闭（issue #107：apply 子进程 import hosting 在下游仓留未跟踪
  __pycache__，污染「落库后工作树干净」断言）→ TestApplyCommit
  .test_apply_leaves_no_pycache_in_downstream（显式零字节码契约）
- PR #120 审查回归（mktemp 泄漏：trap 晚于首个 mktemp，第二个 mktemp
  失败时首个暂存文件泄漏 /tmp）→ TestPR120ReviewRegressions
"""

import glob
import json
import re
import subprocess
from pathlib import Path

import pytest

from gitenv import git_env

TESTS = Path(__file__).resolve().parent
FACTORY = TESTS.parent
SCRIPT = FACTORY / "sync-from-upstream.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=factory@test", "-c", "user.name=factory-test", *args],
        cwd=repo, env=git_env(), check=True, capture_output=True,
    )

def _head_count(repo: Path) -> int:
    return int(subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
        env=git_env(), check=True, capture_output=True, text=True,
    ).stdout.strip())


def _head_subject(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%s"],
        env=git_env(), check=True, capture_output=True, text=True,
    ).stdout.strip()


_IDENTITY = {
    "GIT_AUTHOR_NAME": "factory-test", "GIT_AUTHOR_EMAIL": "factory@test",
    "GIT_COMMITTER_NAME": "factory-test", "GIT_COMMITTER_EMAIL": "factory@test",
}


def _run_env() -> dict:
    """git_env + 提交身份：脚本内 git commit 不依赖宿主全局配置。"""
    env = git_env()
    env.update(_IDENTITY)
    return env


@pytest.fixture()
def repos(tmp_path: Path):
    """上游（含嵌套 full 文件）+ 下游（.factory 仅脚本与 factory_lib，父目录全缺）。"""
    up = tmp_path / "up"
    dn = tmp_path / "dn"
    (up / ".factory" / "tests").mkdir(parents=True)
    (up / ".factory/tools").mkdir()
    (up / ".factory/DISTRIBUTION.json").write_text(json.dumps({
        "full": ["tests/conftest.py", "tools/x.sh"], "local": {}, "skip": [],
    }), encoding="utf-8")
    (up / ".factory/tests/conftest.py").write_text("# upstream canonical\n", encoding="utf-8")
    x = up / ".factory/tools/x.sh"
    x.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    x.chmod(0o755)
    _git(up, "init", "-q", "-b", "main")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "upstream fixture")
    anchor = subprocess.run(
        ["git", "-C", str(up), "rev-parse", "HEAD"],
        env=git_env(), check=True, capture_output=True, text=True,
    ).stdout.strip()

    dn.mkdir()
    (dn / ".factory").mkdir()
    for name in ("sync-from-upstream.sh", "factory_lib.py", "hosting.py",
                 "factory-local.json"):
        (dn / ".factory" / name).write_text(
            (FACTORY / name).read_text(encoding="utf-8"), encoding="utf-8")
    _git(dn, "init", "-q", "-b", "main")
    _git(dn, "add", "-A")
    _git(dn, "commit", "-qm", "downstream fixture")
    return up, dn, anchor


class TestApplyMissingParentDir:
    def test_fillin_creates_missing_parent_dirs(self, repos):
        up, dn, anchor = repos
        proc = subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"),
             str(up), "--apply", "--anchor", "main"],
            cwd=dn, env=git_env(), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        conf = dn / ".factory/tests/conftest.py"
        assert conf.read_text(encoding="utf-8") == "# upstream canonical\n"
        x = dn / ".factory/tools/x.sh"
        assert x.exists() and (x.stat().st_mode & 0o111), "mode 恢复（git show 丢 mode）"
        lock = json.loads((dn / ".factory/upstream-lock.json").read_text(encoding="utf-8"))
        assert lock["anchor"] == anchor


class TestCheckMissingFile:
    def test_check_missing_full_file_exits_1(self, repos):
        up, dn, _ = repos
        proc = subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"),
             str(up), "--check", "--anchor", "main"],
            cwd=dn, env=git_env(), capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "本地缺失" in proc.stdout


class TestRepoMode:
    def test_repo_mode_syncs_target_from_foreign_cwd(self, repos, tmp_path):
        up, dn, anchor = repos
        foreign = tmp_path / "elsewhere"
        foreign.mkdir()
        proc = subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"),
             str(up), "--repo", str(dn), "--apply", "--anchor", "main"],
            cwd=foreign, env=_run_env(), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert (dn / ".factory/tests/conftest.py").read_text(encoding="utf-8") \
            == "# upstream canonical\n"
        lock = json.loads((dn / ".factory/upstream-lock.json").read_text(encoding="utf-8"))
        assert lock["anchor"] == anchor
        assert lock["upstream"] == str(up)

    def test_repo_mode_rejects_non_git_dir(self, repos, tmp_path):
        up, _, _ = repos
        plain = tmp_path / "plain"
        plain.mkdir()
        proc = subprocess.run(
            ["bash", str(repos[1] / ".factory/sync-from-upstream.sh"),
             str(up), "--repo", str(plain), "--check"],
            cwd=tmp_path, env=_run_env(), capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "不是 git 仓库" in proc.stderr

    def test_repo_mode_rejects_missing_path(self, repos, tmp_path):
        up, dn, _ = repos
        proc = subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"),
             str(up), "--repo", str(tmp_path / "nope"), "--check"],
            cwd=tmp_path, env=_run_env(), capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "不存在" in proc.stderr


class TestApplyCommit:
    def _run(self, dn: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"), *args],
            cwd=dn, env=_run_env(), capture_output=True, text=True,
        )

    def test_first_commit_bootstrap_blame_ignore(self, repos):
        up, dn, anchor = repos
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert _head_count(dn) == 2, "单提交落库（fixture 1 + 追平 1）"
        assert _head_subject(dn) == f"factory: 上游同步追平（{anchor[:9]}）"
        ignore = dn / ".git-blame-ignore-revs"
        lines = ignore.read_text(encoding="utf-8").splitlines()
        assert lines and lines[0].startswith("#"), "带说明头"
        assert not [l for l in lines if re.fullmatch(r"[0-9a-f]{40}", l)], \
            "首跑无历史追平提交可记（lock 此前不存在）"
        cfg = subprocess.run(
            ["git", "-C", str(dn), "config", "blame.ignoreRevsFile"],
            env=git_env(), check=True, capture_output=True, text=True,
        ).stdout.strip()
        assert cfg == str(ignore)
        lock = json.loads((dn / ".factory/upstream-lock.json").read_text(encoding="utf-8"))
        assert lock["anchor"] == anchor
        assert lock["upstream"] == str(up)
        status = subprocess.run(
            ["git", "-C", str(dn), "status", "--porcelain"],
            env=git_env(), check=True, capture_output=True, text=True,
        ).stdout
        assert status.strip() == "", "落库后工作树干净"

    def test_apply_leaves_no_pycache_in_downstream(self, repos):
        """issue #107：apply 链的 factory_lib 子进程不得在下游仓留字节码。"""
        up, dn, _ = repos
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        caches = list(dn.glob("**/__pycache__"))
        assert not caches, f"sync 后下游仓残留字节码: {caches}"

    def test_second_sync_records_previous_sync_sha(self, repos):
        up, dn, _ = repos
        assert self._run(dn, str(up), "--apply", "--commit", "--anchor", "main").returncode == 0
        first_sync = subprocess.run(
            ["git", "-C", str(dn), "rev-parse", "HEAD"],
            env=git_env(), check=True, capture_output=True, text=True,
        ).stdout.strip()
        x = up / ".factory/tools/x.sh"
        x.write_text("#!/usr/bin/env bash\ntrue # v2\n", encoding="utf-8")
        _git(up, "add", "-A")
        _git(up, "commit", "-qm", "up v2")
        anchor2 = subprocess.run(
            ["git", "-C", str(up), "rev-parse", "HEAD"],
            env=git_env(), check=True, capture_output=True, text=True,
        ).stdout.strip()
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert _head_count(dn) == 3
        assert _head_subject(dn) == f"factory: 上游同步追平（{anchor2[:9]}）"
        lines = (dn / ".git-blame-ignore-revs").read_text(encoding="utf-8").splitlines()
        assert first_sync in lines, "滞后一条：本轮记上一轮追平提交"

    def test_dirty_factory_refuses_commit(self, repos):
        up, dn, _ = repos
        (dn / ".factory/factory-local.json").write_text("{}\n", encoding="utf-8")
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 1
        assert "拒绝 --commit" in proc.stderr
        assert _head_count(dn) == 1, "失败不得产生提交"
    def test_dirty_tracked_blame_ignore_refuses_commit(self, repos):
        """Sourcery PR#14 评论 2：提交阶段无条件 git add 根 .git-blame-ignore-revs——
        tracked 未提交修改必须被前置脏检查拦截（否则本地热修并入同步提交）。"""
        up, dn, _ = repos
        assert self._run(dn, str(up), "--apply", "--commit", "--anchor", "main").returncode == 0
        ignore = dn / ".git-blame-ignore-revs"
        assert ignore.exists(), "首跑已入库（tracked）"
        ignore.write_text(
            ignore.read_text(encoding="utf-8") + "local hotfix marker\n",
            encoding="utf-8")
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "拒绝 --commit" in proc.stderr
        assert ".git-blame-ignore-revs" in proc.stderr
        assert _head_count(dn) == 2, "拒绝不得产生提交"
        assert "local hotfix marker" in ignore.read_text(encoding="utf-8"), \
            "本地改动须原样保留（不得被追平覆盖/丢弃）"

    def test_manual_untracked_blame_ignore_refuses_commit(self, repos):
        """Sourcery PR#14 评论 2 反例：untracked 多行人工内容不得被无条件 add 入库
        （放行仅限脚本首建残留：untracked 单行注释头，PR #105 评论 1 锚定）。"""
        up, dn, _ = repos
        assert self._run(dn, str(up), "--apply", "--anchor", "main").returncode == 0
        _git(dn, "add", "-A")
        _git(dn, "commit", "-qm", "manual catch-up")
        (dn / ".git-blame-ignore-revs").write_text(
            "# factory: 追平提交忽略清单（git blame --ignore-revs 消噪）\n"
            "manual note beyond header\n", encoding="utf-8")
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "拒绝 --commit" in proc.stderr
        assert _head_count(dn) == 2, "拒绝不得产生提交"
        assert "manual note beyond header" in (dn / ".git-blame-ignore-revs").read_text(
            encoding="utf-8"), "本地改动须原样保留"

    def test_manual_untracked_no_trailing_newline_refuses_commit(self, repos):
        """Sourcery #118 bug_risk：残留判定从 wc -l 换行计数升级为 cmp 整文件精确
        比对——「合法头 + 无尾换行第二行」此前 wc -l 只数 1 个换行而误放行，
        人工内容随之并入同步提交；现必须拒绝（数量 + 前缀形态判定已不可绕过）。"""
        up, dn, _ = repos
        assert self._run(dn, str(up), "--apply", "--anchor", "main").returncode == 0
        _git(dn, "add", "-A")
        _git(dn, "commit", "-qm", "manual catch-up")
        (dn / ".git-blame-ignore-revs").write_text(
            "# factory: 追平提交忽略清单（git blame --ignore-revs 消噪）\n"
            "manual note without trailing newline", encoding="utf-8")
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "拒绝 --commit" in proc.stderr
        assert _head_count(dn) == 2, "拒绝不得产生提交"

    def test_manual_untracked_header_suffix_refuses_commit(self, repos):
        """Sourcery #118 bug_risk：单行头 + 同行任意尾随此前仅前缀匹配而误放行；
        现 cmp 整文件比对拒绝一切与脚本首建单行头不符的内容。"""
        up, dn, _ = repos
        assert self._run(dn, str(up), "--apply", "--anchor", "main").returncode == 0
        _git(dn, "add", "-A")
        _git(dn, "commit", "-qm", "manual catch-up")
        (dn / ".git-blame-ignore-revs").write_text(
            "# factory: 追平提交忽略清单（git blame --ignore-revs 消噪） extra\n",
            encoding="utf-8")
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "拒绝 --commit" in proc.stderr
        assert _head_count(dn) == 2, "拒绝不得产生提交"

    def test_firstrun_residual_header_ships_with_drift_commit(self, repos):
        """设计内状态放行（PR #105 评论 1）：首建残留 = untracked 单行注释头，
        不得被前置检查拒绝——随下一次真追平的 add 一并入库。与两条拒绝用例
        构成精确边界（Sourcery PR#14 评论 2：拦 tracked 修改 + 人工 untracked，
        放行仅脚本首建残留）。"""
        up, dn, _ = repos
        # 1) 全量追平入库（无 --commit），本地落库
        assert self._run(dn, str(up), "--apply", "--anchor", "main").returncode == 0
        _git(dn, "add", "-A")
        _git(dn, "commit", "-qm", "full catch-up")
        # 2) bootstrap --commit：无漂移 → IGNORE 首建、留工作树 untracked（不拦）
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "无变更可提交" in proc.stdout
        ignore = dn / ".git-blame-ignore-revs"
        assert ignore.exists()
        assert len(ignore.read_text(encoding="utf-8").splitlines()) == 1, \
            "残留须为单行注释头（脚本首建形态）"
        # 3) 上游前进 → 真追平：残留随 add 一并入库，不得拒绝
        x = up / ".factory/tools/x.sh"
        x.write_text("#!/usr/bin/env bash\ntrue # v2\n", encoding="utf-8")
        _git(up, "add", "-A")
        _git(up, "commit", "-qm", "up v2")
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "已提交" in proc.stdout
        assert _head_count(dn) == 3, "真追平须落库（fixture + catch-up + 追平）"
        tracked = subprocess.run(
            ["git", "-C", str(dn), "ls-files", "--", ".git-blame-ignore-revs"],
            env=git_env(), capture_output=True, text=True).stdout
        assert ".git-blame-ignore-revs" in tracked, "首建残留应随真追平入库（tracked）"

    def test_no_drift_rerun_makes_no_commit(self, repos):
        up, dn, _ = repos
        assert self._run(dn, str(up), "--apply", "--commit", "--anchor", "main").returncode == 0
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "无变更可提交" in proc.stdout
        assert _head_count(dn) == 2, "无漂移重跑不生成空转提交（链式噪音回归）"

    def test_commit_without_apply_is_usage_error(self, repos):
        up, dn, _ = repos
        proc = self._run(dn, str(up), "--check", "--commit")
        assert proc.returncode == 2
        assert "--commit 仅与 --apply 组合" in proc.stderr


class TestPR105ReviewRegressions:
    """PR #105 审查评论回归：ignore 首建不造空提交 / config 无条件设置 / trap 清理。"""

    def _run(self, dn, *args, env=None):
        return subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"), *args],
            cwd=dn, env=env or _run_env(), capture_output=True, text=True,
        )

    def test_synced_repo_bootstrap_makes_no_commit_but_sets_config(self, repos):
        """评论 1+2：已同步仓库首跑 --commit——不产生仅初始化 ignore 的提交，
        blame.ignoreRevsFile 仍无条件设置（文件存在即生效）。"""
        up, dn, _ = repos
        # 先 --apply（不 --commit）追平后人工入库——构造「已同步且已提交、
        # 但 .git-blame-ignore-revs 缺失」的评论场景
        assert self._run(dn, str(up), "--apply", "--anchor", "main").returncode == 0
        _git(dn, "add", "-A")
        _git(dn, "commit", "-qm", "manual catch-up")
        proc = self._run(dn, str(up), "--apply", "--commit", "--anchor", "main")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "无变更可提交" in proc.stdout
        assert _head_count(dn) == 2, "已同步首跑不得凭空制造初始化提交（评论 1）"
        ignore = dn / ".git-blame-ignore-revs"
        lines = ignore.read_text(encoding="utf-8").splitlines()
        assert lines and lines[0].startswith("#")
        assert not [l for l in lines if re.fullmatch(r"[0-9a-f]{40}", l)]
        cfg = subprocess.run(
            ["git", "-C", str(dn), "config", "blame.ignoreRevsFile"],
            env=git_env(), check=True, capture_output=True, text=True,
        ).stdout.strip()
        assert cfg == str(ignore), "无变更分支也要设置 ignoreRevsFile（评论 2）"
        status = subprocess.run(
            ["git", "-C", str(dn), "status", "--porcelain"],
            env=git_env(), check=True, capture_output=True, text=True,
        ).stdout
        assert status.strip() == "?? .git-blame-ignore-revs", \
            "首建 ignore 留工作树（untracked），随下次真追平入库"

    def test_sourcery_rejection_leaves_no_temp_files(self, repos, tmp_path, private_tmp):
        """评论 3：Sourcery 拒绝（set -e 中途退出）后无暂存文件泄漏。"""
        up, dn, _ = repos
        fake = tmp_path / "bin"
        fake.mkdir()
        # 计数 fake：首次（基线闸）放行，第二次（追平后闸）拒绝——精确命中
        # 「追平后 Sourcery 拒绝」的中途退出路径
        (fake / "sourcery").write_text(
            "#!/bin/sh\n"
            'n=$(($(cat "$0.calls" 2>/dev/null || echo 0) + 1)); echo "$n" > "$0.calls"\n'
            '[ "$n" -lt 2 ] && exit 0\n'
            "exit 1\n", encoding="utf-8")
        (fake / "sourcery").chmod(0o755)
        env = _run_env()
        env["PATH"] = f"{fake}:{env['PATH']}"
        env["TMPDIR"] = str(private_tmp)  # 泄漏断言隔离，见 conftest private_tmp
        before = (set(glob.glob(f"{private_tmp}/.factory-stage.*"))
                  | set(glob.glob(f"{private_tmp}/.factory-dist.*")))
        proc = self._run(dn, str(up), "--apply", "--anchor", "main", env=env)
        assert proc.returncode == 1, "追平后闸返回 1 → 拦截退出"
        assert "Sourcery 回归闸拦截" in proc.stderr
        after = (set(glob.glob(f"{private_tmp}/.factory-stage.*"))
                 | set(glob.glob(f"{private_tmp}/.factory-dist.*")))
        assert after - before == set(), "中途退出不得泄漏暂存文件（评论 3）"

class TestPR120ReviewRegressions:
    """PR #120 审查评论回归：mktemp 暂存泄漏——trap 晚于首个 mktemp。"""

    def _run(self, dn, *args, env=None):
        return subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"), *args],
            cwd=dn, env=env or _run_env(), capture_output=True, text=True,
        )

    def test_second_mktemp_failure_leaks_no_dist_file(self, repos, tmp_path, private_tmp):
        """review 1：第二个 mktemp（STAGE_FILE）失败时首个（DIST_FILE）
        不得泄漏——trap 须紧随首个 mktemp 安装（修复前两个 mktemp 均完成
        后才装 trap，第二个失败即泄漏）。计数 fake：首调放行次调失败。"""
        up, dn, _ = repos
        fake = tmp_path / "bin"
        fake.mkdir()
        (fake / "mktemp").write_text(
            "#!/bin/sh\n"
            'n=$(($(cat "$0.calls" 2>/dev/null || echo 0) + 1)); echo "$n" > "$0.calls"\n'
            '[ "$n" -lt 2 ] && exec /usr/bin/mktemp "$@"\n'
            "exit 1\n", encoding="utf-8")
        (fake / "mktemp").chmod(0o755)
        env = _run_env()
        env["PATH"] = f"{fake}:{env['PATH']}"
        env["TMPDIR"] = str(private_tmp)  # 泄漏断言隔离，见 conftest private_tmp
        before = set(glob.glob(f"{private_tmp}/.factory-dist.*"))
        proc = self._run(dn, str(up), "--check", "--anchor", "main", env=env)
        assert proc.returncode != 0, "第二个 mktemp 失败须中断脚本"
        after = set(glob.glob(f"{private_tmp}/.factory-dist.*"))
        assert after - before == set(), "第二个 mktemp 失败不得泄漏首个暂存（review 1）"

class TestSelfOverwriteSafety:
    """issue #103：apply 覆盖 $dst 为运行中脚本自身时的原子替换契约。

    直写 `> "$dst"` 截断同 inode，bash 惰性逐段读的旧位移落在新内容中途
    → syntax error exit 2、锚点未写的半同步态（2026-09-01 复现）；
    tmp+mv 同目录 rename 换新 inode，旧 inode 由运行中 bash 保活至跑完。"""

    def test_apply_replaces_running_script_atomically(self, tmp_path):
        up = tmp_path / "up"
        dn = tmp_path / "dn"
        (up / ".factory").mkdir(parents=True)
        # 上游 v2 = 本仓现行脚本（含 tmp+mv 修复）尾部追加标记注释；
        # 下游持 v1（现行脚本原文）——漂移覆盖恰命中运行中脚本自身
        script_v1 = (FACTORY / "sync-from-upstream.sh").read_text(encoding="utf-8")
        script_v2 = script_v1 + "\n# self-overwrite v2 marker\n"
        (up / ".factory/sync-from-upstream.sh").write_text(script_v2, encoding="utf-8")
        (up / ".factory/DISTRIBUTION.json").write_text(json.dumps({
            "full": ["sync-from-upstream.sh"], "local": {}, "skip": [],
        }), encoding="utf-8")
        _git(up, "init", "-q", "-b", "main")
        _git(up, "add", "-A")
        _git(up, "commit", "-qm", "upstream v2")

        dn.mkdir()
        (dn / ".factory").mkdir()
        for name in ("sync-from-upstream.sh", "factory_lib.py", "hosting.py",
                     "factory-local.json"):
            (dn / ".factory" / name).write_text(
                (FACTORY / name).read_text(encoding="utf-8"), encoding="utf-8")
        _git(dn, "init", "-q", "-b", "main")
        _git(dn, "add", "-A")
        _git(dn, "commit", "-qm", "downstream v1")

        proc = subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"),
             str(up), "--apply", "--anchor", "main"],
            cwd=dn, env=_run_env(), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "syntax error" not in proc.stderr, "自覆盖不得打断运行中脚本"
        assert (dn / ".factory/sync-from-upstream.sh").read_text(encoding="utf-8") \
            == script_v2, "脚本自身完整替换为上游 v2"
        lock = json.loads((dn / ".factory/upstream-lock.json").read_text(encoding="utf-8"))
        assert lock["anchor"], "锚点照常写入（半同步态防线）"
        assert not list((dn / ".factory").glob("*.factory-new.*")), "无 tmp 中转残留"

class TestPR106ReviewRegressions:
    """PR #106 审查评论回归：--repo 子目录规范化到仓根 / 旧锁 upstream 回填。"""

    def test_repo_arg_subdir_resolves_to_toplevel(self, repos):
        """评论 2：子目录入参须落仓根 .factory，不得错位到 <subdir>/.factory。"""
        up, dn, anchor = repos
        sub = dn / "nested" / "deep"
        sub.mkdir(parents=True)
        proc = subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"),
             str(up), "--repo", str(sub), "--apply", "--anchor", "main"],
            cwd=sub, env=_run_env(), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        lock = json.loads((dn / ".factory/upstream-lock.json").read_text(encoding="utf-8"))
        assert lock["anchor"] == anchor
        assert lock["upstream"] == str(up)
        assert not (sub / ".factory").exists(), "锁/分发不得错位到子目录（评论 2）"

    def test_apply_backfills_missing_upstream_field(self, repos):
        """评论 4：旧锁 anchor 未变但缺 upstream 字段时，空追平也须回填。"""
        up, dn, anchor = repos
        lock = dn / ".factory/upstream-lock.json"
        first = subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"),
             str(up), "--apply", "--anchor", "main"],
            cwd=dn, env=_run_env(), capture_output=True, text=True,
        )
        assert first.returncode == 0, first.stdout + first.stderr
        data = json.loads(lock.read_text(encoding="utf-8"))
        assert data["upstream"] == str(up)
        del data["upstream"]  # 模拟 M2 前旧锁：anchor 未变、缺来源字段
        lock.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        second = subprocess.run(
            ["bash", str(dn / ".factory/sync-from-upstream.sh"),
             str(up), "--apply", "--anchor", "main"],
            cwd=dn, env=_run_env(), capture_output=True, text=True,
        )
        assert second.returncode == 0, second.stdout + second.stderr
        data = json.loads(lock.read_text(encoding="utf-8"))
        assert data["upstream"] == str(up), "旧锁缺 upstream 须回填（评论 4）"
        assert data["anchor"] == anchor
