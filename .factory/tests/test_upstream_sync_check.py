"""upstream-sync-check.sh 退出码契约回归（xx-skills PR#14 Sourcery 评论 1）。

缺陷：sync --check 的致命 rc=2（用法/上游不可用/锚点不可解析）原被 `&& {}`
短路吞掉——输出不带 [local]/[full] 标记时落入收尾分支，以「仅 local 面漂移」
exit 0 误报无漂移，调用方（dispatch）把致命检查失败当无事发生。

修复：rc≥2 原样上抛（stderr + 同码退出）。本文件锁定 rc 契约矩阵：
  rc=0  干净      → exit 0（"无动作"）
  rc=1  full 漂移 → --dry-run 报告并 exit 1（本测试不触 apply/gauntlet/PR 面）
  rc=2  致命失败  → exit 2，且绝不走 issue/PR 流（fake hosting 计数断言）

凭据面用 fake hosting.py 顶替（auth ok 恒 0，其余调用计数 + 非 0）——
与 gitenv PATH 白名单配合，测试链零出网。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from gitenv import git_env

TESTS = Path(__file__).resolve().parent
FACTORY = TESTS.parent
SCRIPT = FACTORY / "upstream-sync-check.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=factory@test", "-c", "user.name=factory-test", *args],
        cwd=repo, env=git_env(), check=True, capture_output=True,
    )


@pytest.fixture()
def synced(tmp_path: Path):
    """up（上游含 full 文件）+ dn（下游 .factory 真实工具链 + fake hosting）+
    基态追平（dn full 面与 up 一致、lock 有效）→ 脚本可跑 rc=0 的干净基态。"""
    up = tmp_path / "up"
    dn = tmp_path / "dn"
    (up / ".factory" / "tools").mkdir(parents=True)
    (up / ".factory" / "DISTRIBUTION.json").write_text(json.dumps({
        "full": ["tools/x.sh"], "local": {}, "skip": [],
    }, ensure_ascii=False), encoding="utf-8")
    x = up / ".factory/tools/x.sh"
    x.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    x.chmod(0o755)
    _git(up, "init", "-q", "-b", "main")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "up fixture")

    dn.mkdir()
    (dn / ".factory").mkdir()
    # factory_lib.py import 即 fail-closed 读 factory-local.json（真实文件拷贝）
    for name in ("sync-from-upstream.sh", "upstream-sync-check.sh",
                 "factory_lib.py", "factory-local.json"):
        (dn / ".factory" / name).write_text(
            (FACTORY / name).read_text(encoding="utf-8"), encoding="utf-8")
    calls = tmp_path / "hosting-calls"
    # fake hosting：auth ok 恒过（凭据探测走真路径）；其它命令计数 + 非 0。
    # factory_lib.py 顶部 import hosting → 副作用必须收在 __main__ 内，
    # 否则 sys.exit 在 import 时即杀进程（实测 dist-manifest rc=3）。
    (dn / ".factory" / "hosting.py").write_text(
        "import sys\n"
        "def _log():\n"
        f'    open({str(calls)!r}, "a").write("|".join(sys.argv[1:]) + "\\n")\n'
        'if __name__ == "__main__":\n'
        "    _log()\n"
        '    sys.exit(0 if sys.argv[1:2] == ["auth"] else 3)\n',
        encoding="utf-8")
    (dn / ".factory" / "upstream-lock.json").write_text(
        json.dumps({"upstream": str(up)}, ensure_ascii=False), encoding="utf-8")
    _git(dn, "init", "-q", "-b", "main")
    _git(dn, "add", "-A")
    _git(dn, "commit", "-qm", "dn fixture")

    proc = subprocess.run(
        ["bash", str(dn / ".factory/sync-from-upstream.sh"), str(up), "--apply"],
        cwd=dn, env=git_env(), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return up, dn, calls


class TestSyncRcContract:
    def _run(self, dn: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(dn / ".factory/upstream-sync-check.sh"), *args],
            cwd=dn, env=git_env(), capture_output=True, text=True,
        )

    def test_clean_reports_no_action(self, synced):
        _, dn, calls = synced
        proc = self._run(dn)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "full 面干净，无动作" in proc.stdout
        lines = calls.read_text().splitlines()
        assert lines, "凭据探测须真实发生"
        assert all("auth" in line for line in lines), f"干净基态不得触发远端命令: {lines}"

    def test_fatal_sync_rc2_propagates(self, synced):
        """Sourcery PR#14 评论 1：sync --check 致命 rc=2 原样上抛，
        不得落入「仅 local 面漂移」exit 0 误报无漂移。"""
        up, dn, calls = synced
        (dn / ".factory/upstream-lock.json").write_text(
            json.dumps({"upstream": str(dn / "gone")}, ensure_ascii=False),
            encoding="utf-8")
        proc = self._run(dn)
        assert proc.returncode == 2, (
            f"致命 rc 须原样上抛（实得 rc={proc.returncode}）\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}")
        assert "上游仓不可用" in proc.stderr, "sync 的诊断须原样透传"
        assert "full 面干净" not in proc.stdout
        assert "仅 local 面漂移" not in proc.stdout
        lines = calls.read_text().splitlines()
        assert all("auth" in line for line in lines), f"rc=2 不得触发 issue/PR 流: {lines}"

    def test_full_drift_dryrun_exits_1(self, synced):
        """full 漂移 rc=1 语义不回归：--dry-run 报告并 exit 1（人工介入信号）。"""
        up, dn, calls = synced
        (dn / ".factory/tools/x.sh").write_text(
            "#!/usr/bin/env bash\ntrue # local drift\n", encoding="utf-8")
        proc = self._run(dn, "--dry-run")
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "[dry-run] full 漂移存在" in proc.stdout
        lines = calls.read_text().splitlines()
        assert all("auth" in line for line in lines), f"dry-run 不得触发远端命令: {lines}"


class TestDispatchRootRepoSkip:
    """调用方 factory_lib._upstream_sync_check 根仓免跑契约（2026-09-05）。

    噪音 C 溯源：根仓锁文件缺 upstream 字段（本仓是源仓，无上游可同步），
    但 dispatch 每轮仍跑 upstream-sync-check.sh → 脚本 exit 2 刷日志 103 轮。
    裁决：根仓免跑（锁缺 upstream = 无上游声明），fork 侧 sync --apply
    写锁带 upstream=根仓 URL → 走正常检查自动追平。"""
    import factory_lib

    def _mk(self, tmp_path, lock: dict | None):
        from types import SimpleNamespace
        factory = tmp_path / ".factory"
        factory.mkdir()
        check = factory / "upstream-sync-check.sh"
        check.write_text("#!/usr/bin/env bash\necho invoked > $(dirname $0)/invoked-marker\nexit 0\n", encoding="utf-8")
        check.chmod(0o755)
        if lock is not None:
            (factory / "upstream-lock.json").write_text(
                json.dumps(lock, ensure_ascii=False), encoding="utf-8")
        return SimpleNamespace(factory=factory)

    def test_root_repo_skips_without_upstream_field(self, tmp_path, capsys):
        """根仓：锁缺 upstream 字段 → 免跑（脚本不被调、无噪音、rc 0）。"""
        cfg = self._mk(tmp_path, {"anchor": "20f6a63"})
        assert self.factory_lib._upstream_sync_check(cfg) == 0
        assert "根仓无上游声明，免上游同步" in capsys.readouterr().out
        assert not (cfg.factory / "invoked-marker").exists(), "根仓不得调用 check 脚本"

    def test_fork_repo_runs_check_with_upstream_field(self, tmp_path, capsys):
        """fork：锁带 upstream=根仓 URL → 正常跑脚本（自动追平不回归）。"""
        cfg = self._mk(tmp_path, {"anchor": "x", "upstream": "https://github.com/im47cn/awesome-rules"})
        assert self.factory_lib._upstream_sync_check(cfg) == 0
        assert "上游同步已推进" in capsys.readouterr().out
        assert (cfg.factory / "invoked-marker").exists(), "fork 侧必须跑 check 脚本"

    def test_corrupt_lock_skips_with_disclosure(self, tmp_path, capsys):
        """坏 JSON 锁：不可读 → 免跑 + 披露需人工处置（不静默、不刷噪音）。"""
        cfg = self._mk(tmp_path, None)
        (cfg.factory / "upstream-lock.json").write_text("{broken", encoding="utf-8")
        assert self.factory_lib._upstream_sync_check(cfg) == 0
        assert "upstream-lock.json 不可读" in capsys.readouterr().out
        assert not (cfg.factory / "invoked-marker").exists()

    def test_valid_json_non_dict_lock_skips_with_disclosure(self, tmp_path, capsys):
        """sourcery issue(bug_risk)：合法 JSON 非对象（[]/null/"bad"）→ .get 崩——
        须校验 dict 形态后披露免跑（不 AttributeError）。"""
        cfg = self._mk(tmp_path, None)
        (cfg.factory / "upstream-lock.json").write_text("[]", encoding="utf-8")
        assert self.factory_lib._upstream_sync_check(cfg) == 0
        assert "不可读或非对象" in capsys.readouterr().out
        assert not (cfg.factory / "invoked-marker").exists(), "非对象锁不得调用 check 脚本"

    def test_env_declared_upstream_still_runs_check(self, tmp_path, capsys, monkeypatch):
        """sourcery issue(broader_impact)：锁缺 upstream 但 FACTORY_UPSTREAM env 已设
        （check 脚本 L45 支持的合法上游源）→ 不得误免跑，须调脚本。"""
        monkeypatch.setenv("FACTORY_UPSTREAM", "https://github.com/im47cn/awesome-rules")
        cfg = self._mk(tmp_path, {"anchor": "x"})
        assert self.factory_lib._upstream_sync_check(cfg) == 0
        assert (cfg.factory / "invoked-marker").exists(), "env 声明上游的 fork 必须跑 check 脚本"
