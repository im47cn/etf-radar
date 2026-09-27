"""downstream-check.sh 回归测试 —— 中心仓集中巡检（脚本首测）。

缺陷→测试映射:
- 退出码契约（头注释：0=全干净 1=漂移/单仓失败 2=清单缺失/损坏/用法）
  → TestPatrolExitCodes：漂移 rc1+汇总 / 缺清单 rc2 / 坏 JSON rc2 /
    坏条目（空串/非字符串 path——静默漏检防线，PR #106 评论 3）rc2 /
    --apply-commit 追平后复查 rc0
- 空转链回归（追平落库后重跑巡检不得再产生新提交——与
  test_sync_from_upstream.TestApplyCommit 同源缺陷的舰队级复测）
  → TestPatrolExitCodes.test_apply_commit_levels_fleet
- 单仓失败不中断（清单含坏路径：记 [错误] 继续跑完其余仓）
  → TestPatrolResilience.test_missing_repo_path_error_continues
- PR #120 审查回归（mktemp 暂存泄漏：trap 晚于 mktemp 安装，用法错误等
  早退路径泄漏 /tmp 文件）→ TestPR120ReviewRegressions
- 锁互斥（PR #120 review 1 修正：LOCK 并入清理 trap 须在持锁成功后；
  竞争退出路径删他人锁破坏互斥）→ TestPR120ReviewRegressions
"""

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gitenv import git_env

TESTS = Path(__file__).resolve().parent
FACTORY = TESTS.parent

_IDENTITY = {
    "GIT_AUTHOR_NAME": "factory-test", "GIT_AUTHOR_EMAIL": "factory@test",
    "GIT_COMMITTER_NAME": "factory-test", "GIT_COMMITTER_EMAIL": "factory@test",
    "FACTORY_NO_NOTIFY": "1",  # 测试静默：不弹真实桌面通知
}


def _run_env() -> dict:
    """git_env + 提交身份 + 通知开关：脚本内 git commit/通知不依赖宿主环境。"""
    env = git_env()
    env.update(_IDENTITY)
    return env


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=factory@test", "-c", "user.name=factory-test", *args],
        cwd=repo, env=git_env(), check=True, capture_output=True,
    )


def _rev(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=git_env(), check=True, capture_output=True, text=True,
    ).stdout.strip()


def _make_center(tmp_path: Path) -> tuple[Path, str]:
    center = tmp_path / "center"
    (center / ".factory/tests").mkdir(parents=True)
    (center / ".factory/tools").mkdir()
    (center / ".factory/DISTRIBUTION.json").write_text(json.dumps({
        "full": ["tests/conftest.py", "tools/x.sh"], "local": {}, "skip": [],
    }), encoding="utf-8")
    (center / ".factory/tests/conftest.py").write_text("# canonical\n", encoding="utf-8")
    x = center / ".factory/tools/x.sh"
    x.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    x.chmod(0o755)
    for name in ("sync-from-upstream.sh", "downstream-check.sh",
                 "factory_lib.py", "hosting.py", "factory-local.json"):
        shutil.copy(FACTORY / name, center / ".factory" / name)
    (center / ".factory/downstream.json").write_text(json.dumps({"repos": [
        {"path": "../dn-clean"}, {"path": "../dn-drift"},
    ]}, ensure_ascii=False, indent=2), encoding="utf-8")
    _git(center, "init", "-q", "-b", "main")
    _git(center, "add", "-A")
    _git(center, "commit", "-qm", "center fixture")
    return center, _rev(center, "rev-parse", "HEAD")


def _make_downstream(tmp_path: Path, name: str) -> Path:
    dn = tmp_path / name
    (dn / ".factory").mkdir(parents=True)
    for n in ("sync-from-upstream.sh", "factory_lib.py", "hosting.py",
              "factory-local.json"):
        (dn / ".factory" / n).write_text((FACTORY / n).read_text(encoding="utf-8"),
                                         encoding="utf-8")
    _git(dn, "init", "-q", "-b", "main")
    _git(dn, "add", "-A")
    _git(dn, "commit", "-qm", "downstream fixture")
    return dn


@pytest.fixture()
def fleet(tmp_path: Path):
    """中心仓 + 两个下游（一个已追平落库、一个漂移）。"""
    center, anchor = _make_center(tmp_path)
    dn_clean = _make_downstream(tmp_path, "dn-clean")
    dn_drift = _make_downstream(tmp_path, "dn-drift")
    # dn-clean 预追平+落库：直接用被测的 --repo/--commit 链路（狗粮）
    proc = subprocess.run(
        ["bash", str(center / ".factory/sync-from-upstream.sh"),
         str(center), "--repo", str(dn_clean), "--apply", "--commit", "--anchor", "main"],
        cwd=tmp_path, env=_run_env(), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return center, dn_clean, dn_drift, anchor


def _patrol(center: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(center / ".factory/downstream-check.sh"), *args],
        cwd=center, env=_run_env(), capture_output=True, text=True,
    )


class TestPatrolExitCodes:
    def test_check_reports_drift_summary(self, fleet):
        center, dn_clean, dn_drift, _ = fleet
        proc = _patrol(center)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "[干净] ../dn-clean" in proc.stdout
        assert "[漂移] ../dn-drift" in proc.stdout
        assert "巡检汇总: 干净 1 / 已追平 0 / 漂移 1 / 错误 0" in proc.stdout

    def test_missing_manifest_exits_2(self, fleet):
        center, _, _, _ = fleet
        (center / ".factory/downstream.json").unlink()
        proc = _patrol(center)
        assert proc.returncode == 2
        assert "下游清单缺失" in proc.stderr

    def test_corrupt_manifest_exits_2(self, fleet):
        center, _, _, _ = fleet
        (center / ".factory/downstream.json").write_text("{bad json", encoding="utf-8")
        proc = _patrol(center)
        assert proc.returncode == 2
        assert "下游清单损坏" in proc.stderr

    def test_manifest_empty_path_entry_exits_2(self, fleet):
        center, _, _, _ = fleet
        (center / ".factory/downstream.json").write_text(json.dumps({"repos": [
            {"path": "../dn-clean"}, {"path": ""},
        ]}, ensure_ascii=False, indent=2), encoding="utf-8")
        proc = _patrol(center)
        assert proc.returncode == 2
        assert "下游清单损坏" in proc.stderr

    def test_manifest_non_string_path_entry_exits_2(self, fleet):
        center, _, _, _ = fleet
        (center / ".factory/downstream.json").write_text(json.dumps({"repos": [
            {"path": "../dn-clean"}, {"path": 123},
        ]}, ensure_ascii=False, indent=2), encoding="utf-8")
        proc = _patrol(center)
        assert proc.returncode == 2
        assert "下游清单损坏" in proc.stderr

    def test_apply_commit_levels_fleet(self, fleet):
        center, dn_clean, dn_drift, _ = fleet
        proc = _patrol(center, "--apply-commit")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "[已追平] ../dn-drift" in proc.stdout
        assert "[干净] ../dn-clean" in proc.stdout
        assert _rev(dn_drift, "log", "-1", "--format=%s") \
            .startswith("factory: 上游同步追平（")
        assert (dn_drift / ".git-blame-ignore-revs").exists()
        # 复查：全干净，且不产生新提交（空转链舰队级回归）
        n_drift = _rev(dn_drift, "rev-list", "--count", "HEAD")
        n_clean = _rev(dn_clean, "rev-list", "--count", "HEAD")
        second = _patrol(center)
        assert second.returncode == 0, second.stdout + second.stderr
        assert "巡检汇总: 干净 2 / 已追平 0 / 漂移 0 / 错误 0" in second.stdout
        assert _rev(dn_drift, "rev-list", "--count", "HEAD") == n_drift
        assert _rev(dn_clean, "rev-list", "--count", "HEAD") == n_clean

    def test_unknown_flag_is_usage_error(self, fleet):
        center, _, _, _ = fleet
        proc = _patrol(center, "--frobnicate")
        assert proc.returncode == 2
        assert "未知参数" in proc.stderr


class TestPatrolResilience:
    def test_missing_repo_path_error_continues(self, fleet):
        center, dn_clean, _, _ = fleet
        (center / ".factory/downstream.json").write_text(json.dumps({"repos": [
            {"path": "../nope"}, {"path": "../dn-clean"},
        ]}, ensure_ascii=False, indent=2), encoding="utf-8")
        proc = _patrol(center)
        assert proc.returncode == 1
        assert "[错误] ../nope" in proc.stderr
        assert "[干净] ../dn-clean" in proc.stdout, "单仓失败不中断其余巡检"

class TestADR012LocalManifest:
    """ADR-012：真实清单住 downstream.local.json（gitignored），存在时
    优先于 tracked 模板——公开中心仓零内部标识。"""

    def test_local_manifest_precedence(self, fleet):
        center, dn_clean, _, _ = fleet
        (center / ".factory/downstream.local.json").write_text(
            json.dumps({"repos": [{"path": "../dn-clean"}]},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        proc = _patrol(center)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "[干净] ../dn-clean" in proc.stdout

    def test_empty_tracked_template_fail_closed_with_guidance(self, fleet):
        center, _, _, _ = fleet
        (center / ".factory/downstream.json").write_text(
            json.dumps({"repos": []}), encoding="utf-8")
        proc = _patrol(center)
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "downstream.local.json" in proc.stderr


class TestPR120ReviewRegressions:
    """PR #120 审查评论回归：mktemp 暂存泄漏——trap 晚于 mktemp 安装。"""

    def test_usage_error_leaks_no_temp_file(self, tmp_path, private_tmp):
        """review 1：用法错误（trap 安装前的早退路径）不得泄漏暂存文件——
        修复前 trap 装于清单检查与加锁之后，mktemp 至 trap 之间的 exit 2
        泄漏 OUT_FILE。"""
        env = git_env()
        env["TMPDIR"] = str(private_tmp)  # 泄漏断言隔离，见 conftest private_tmp
        before = set(glob.glob(f"{private_tmp}/.factory-downstream-check.*"))
        proc = subprocess.run(
            ["bash", str(FACTORY / "downstream-check.sh"), "--frobnicate"],
            cwd=tmp_path, env=env, capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "未知参数" in proc.stderr
        after = set(glob.glob(f"{private_tmp}/.factory-downstream-check.*"))
        assert after - before == set(), "trap 安装前早退不得泄漏暂存（review 1）"

    def test_lock_competition_keeps_foreign_lock(self, fleet, private_tmp):
        """review 1 修正：他实例持锁时本实例 exit 0 退出，不得删除对方
        锁文件——修复前 trap 提前并入 $LOCK，竞争退出时 rm 掉对方锁，
        破坏互斥。活 PID 锁：content=本测试进程 PID（kill -0 存活）。"""
        center, _, _, _ = fleet
        lock = center / ".factory/locks/downstream-check.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        env = git_env()
        env["TMPDIR"] = str(private_tmp)  # 泄漏断言隔离，见 conftest private_tmp
        before = set(glob.glob(f"{private_tmp}/.factory-downstream-check.*"))
        proc = subprocess.run(
            ["bash", str(center / ".factory/downstream-check.sh")],
            cwd=center, env=env, capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert "巡检锁被持" in proc.stderr
        assert lock.exists(), "竞争退出不得删除对方锁（互斥）"
        assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())
        after = set(glob.glob(f"{private_tmp}/.factory-downstream-check.*"))
        assert after - before == set(), "竞争退出仍须清自身暂存（review 1）"
