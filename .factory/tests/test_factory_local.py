"""M4 本地化外置的回归测试：guard/factory_lib 从 factory-local.json 载入
周界与判据措辞；fail-closed 语义（配置缺失/损坏 → 非零）；stamp 指纹
绑定（perimeter_blob / stamp_stale_banner / 全绿写入——纯函数部分）。

周界数据化后「改配置 = 改门」：evidence-stamp.json 记录 factory-local.json
的 git blob hash，run.py 启动比对宣告过期（设计 §11.3）。
"""
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mutations"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gitenv import _sealed_path, git_env  # noqa: E402  (tests/ 兄弟模块，pytest rootdir 注入)

import run as mut  # noqa: E402
import guard  # noqa: E402
import factory_lib  # noqa: E402


class TestGuardLoadsPerimeterFromConfig:
    """guard.py 零本地化：PERIMETER 来自 factory-local.json（M4）。"""

    def test_perimeter_loaded_and_nonempty(self):
        assert len(guard.PERIMETER) > 10
        assert ".factory/" in guard.PERIMETER
        # 通用不变量：质检线自锁（治理文件属仓特定，不作硬断言——ADR-008
        # 下游移植的周界清单各不相同）
        assert any(p.endswith("/") for p in guard.PERIMETER)

    def test_perimeter_consistent_with_config_file(self):
        cfg = json.loads(
            (Path(guard.__file__).parent / "factory-local.json").read_text(encoding="utf-8"))
        assert tuple(cfg["perimeter"]) == guard.PERIMETER

    def test_mission_self_check_passes(self):
        guard.self_check()  # 不抛 = PERIMETER 与 MISSION.md 一致且路径存在

    def test_fail_closed_on_missing_config(self, tmp_path):
        """配置缺失/损坏 → RuntimeError（guard main 捕获 → exit 2）。"""
        src = Path(guard.__file__).read_text(encoding="utf-8")
        fake = tmp_path / "guard.py"
        # 重写载入路径指向不存在的配置
        fake.write_text(src.replace(
            '"factory-local.json"', '"no-such-config.json"'), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(fake), "--files", "README.md"],
            capture_output=True, text=True, cwd=str(tmp_path))
        assert proc.returncode == 2  # fail-closed：门坏等同拦截


class TestRejectGuidanceFromConfig:
    """factory_lib.REJECT_GUIDANCE 来自 factory-local.json（M4）。"""

    def test_guidance_keys_loaded(self):
        assert set(factory_lib.REJECT_GUIDANCE) == {"a", "b", "c"}
        assert all(len(v) > 20 for v in factory_lib.REJECT_GUIDANCE.values())

    def test_receipt_uses_config_guidance(self):
        md = factory_lib.reject_receipt({"verdict": "reject",
                                         "reasons": ["判据a: 不通过"]})
        assert factory_lib.REJECT_GUIDANCE["a"] in md


class TestEvidenceSuitesDualLayout:
    """evidence_suites 双布局（skills + monorepo），零本地化（M4）。"""

    def test_skills_layout(self):
        assert factory_lib.evidence_suites(["skills/api-guard/scripts/a.py"]) == [
            "skills/api-guard/scripts"]

    def test_monorepo_layout(self):
        assert factory_lib.evidence_suites(["backend/src/x.py", "frontend/y.tsx"]) == [
            "backend", "frontend"]

    def test_non_project_files_no_suite(self):
        assert factory_lib.evidence_suites(["README.md", "docs/x.md"]) == []


class TestPerimeterStamp:
    """run.py 指纹绑定：perimeter_blob 与 stamp 横幅（纯函数契约）。"""

    def test_perimeter_blob_shape(self):
        blob = mut.perimeter_blob()
        if blob is not None:  # git 仓内 = 40 hex
            assert len(blob) == 40 and all(c in "0123456789abcdef" for c in blob)

    def test_stale_banner_silent_without_stamp(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(mut, "STAMP", tmp_path / "no-stamp.json")
        mut.stamp_stale_banner()  # 无 stamp：静默
        assert capsys.readouterr().out == ""

    def test_stale_banner_announces_drift(self, tmp_path, capsys, monkeypatch):
        stamp = tmp_path / "evidence-stamp.json"
        stamp.write_text(json.dumps({"perimeter_blob": "0" * 40}), encoding="utf-8")
        monkeypatch.setattr(mut, "STAMP", stamp)
        cur = mut.perimeter_blob()
        if cur is None:
            pytest.skip("无 git 环境")
        if cur != "0" * 40:
            mut.stamp_stale_banner()
            assert "周界指纹漂移" in capsys.readouterr().out

    def test_stale_banner_quiet_when_matching(self, tmp_path, capsys, monkeypatch):
        cur = mut.perimeter_blob()
        if cur is None:
            pytest.skip("无 git 环境")
        stamp = tmp_path / "evidence-stamp.json"
        stamp.write_text(json.dumps({"perimeter_blob": cur}), encoding="utf-8")
        monkeypatch.setattr(mut, "STAMP", stamp)
        mut.stamp_stale_banner()
        assert capsys.readouterr().out == ""


class TestStampRoundtrip:
    """stamp 的 git 往返闭环（完整周期，临时仓模拟）：
    全绿写 stamp → 改 factory-local.json（blob 变）→ 启动宣告过期 →
    重证写新 stamp → 再启动安静。「改配置 = 改门」的可执行证明。
    monkeypatch STAMP/LOCAL_CFG 指向 tmp git 仓（perimeter_blob 走
    REPO_ROOT 相对路径——一并 patch 到临时仓根）。"""

    def _git(self, cwd, *args):
        # git_env：剥除钩子环境泄漏的 GIT_DIR 等（PR #71 推送实测：
        # 泄漏时夹具 commit 落进真实仓 HEAD）。
        return subprocess.run(["git", "-C", str(cwd), *args],
                              capture_output=True, text=True, check=True,
                              env=git_env())

    def test_full_cycle_announce_then_refresh(self, tmp_path, capsys, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        cfg = repo / "factory-local.json"
        cfg.write_text('{"perimeter": ["a/"]}', encoding="utf-8")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "init")

        stamp = repo / "evidence-stamp.json"
        monkeypatch.setattr(mut, "STAMP", stamp)
        monkeypatch.setattr(mut, "LOCAL_CFG", cfg)
        monkeypatch.setattr(mut, "REPO_ROOT", repo)

        # ① 无 stamp：安静（首次运行不宣告）
        mut.stamp_stale_banner()
        assert capsys.readouterr().out == ""

        # ② 全绿：stamp 落盘，blob 与当前配置一致
        blob1 = mut.write_stamp(evidence="EVIDENCE-test.md")
        assert blob1 and json.loads(stamp.read_text())["perimeter_blob"] == blob1
        # stamp 与配置匹配 → 仍安静
        mut.stamp_stale_banner()
        assert capsys.readouterr().out == ""

        # ③ 改周界配置并入库（stamp 绑定 index blob——工作树未提交编辑
        #    不构成周界事实，不宣告）→ 启动宣告过期
        cfg.write_text('{"perimeter": ["a/", "b/"]}', encoding="utf-8")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "perimeter change")
        mut.stamp_stale_banner()
        assert "周界指纹漂移" in capsys.readouterr().out

        # ④ 重证（全绿）：stamp 刷新为新 blob → 再启动安静
        blob2 = mut.write_stamp(evidence="EVIDENCE-test.md")
        assert blob2 and blob2 != blob1
        mut.stamp_stale_banner()
        assert capsys.readouterr().out == ""

    def test_untracked_config_still_binds_via_write(self, tmp_path, monkeypatch):
        """git add 后 blob 才可取；未跟踪时 perimeter_blob=None（不写不宣告）。
        git ls-files -s 只看 index——设计上 stamp 绑定的是已入库的周界。"""
        repo = tmp_path / "repo2"
        repo.mkdir()
        self._git(repo, "init", "-q")
        cfg = repo / "factory-local.json"
        cfg.write_text('{"perimeter": ["a/"]}', encoding="utf-8")
        monkeypatch.setattr(mut, "LOCAL_CFG", cfg)
        monkeypatch.setattr(mut, "REPO_ROOT", repo)
        assert mut.perimeter_blob() is None  # 未 add：无法绑定
        assert mut.write_stamp() is None     # 不写 stamp


class TestGitEnvSealing:
    """钩子环境 GIT_* 泄漏防夹具污染（PR #71 推送实测事故回归锁）。

    机制复现（无 git_env）：泄漏 GIT_DIR 指向受害者仓时，`git -C <夹具仓>
    commit` 实际提交进受害者仓——lefthook pre-push 门禁下即真实仓 HEAD。
    """
    def _git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args],
                              capture_output=True, text=True, check=True,
                              env=git_env())

    def _init_repo(self, path):
        path.mkdir()
        self._git(path, "init", "-q")
        self._git(path, "config", "user.email", "t@t")
        self._git(path, "config", "user.name", "t")

    def test_leaked_git_dir_hijacks_without_sealing(self, tmp_path):
        """无密闭 → 提交落受害者仓（钉死事故机制，证 git_env 必要性）。"""
        victim, fixture = tmp_path / "victim", tmp_path / "fixture"
        self._init_repo(victim)
        self._init_repo(fixture)
        (fixture / "factory-local.json").write_text("{}", encoding="utf-8")
        # 密闭面基线（#109：PATH 白名单 + GIT_CONFIG /dev/null）之上
        # 注入泄漏变量——复现维度仅 GIT_DIR 劫持。裸 os.environ 会把
        # 宿主 gpgsign 带进来：无 homebrew PATH 形态下 gpg 不可见 →
        # commit rc=128 假红（#109 陷阱②在负例上的投影）
        leaked = git_env()
        leaked["GIT_DIR"] = str(victim / ".git")
        subprocess.run(["git", "-C", str(fixture), "add", "-A"],
                       check=True, env=leaked, capture_output=True)
        subprocess.run(["git", "-C", str(fixture), "commit", "-qm", "x"],
                       check=True, env=leaked, capture_output=True)
        # 无密闭：victim 收到提交（= 事故形态），fixture 反而无 HEAD
        assert self._git(victim, "rev-parse", "HEAD").stdout.strip()
        rc = subprocess.run(["git", "-C", str(fixture), "rev-parse", "HEAD"],
                            capture_output=True, env=git_env())
        assert rc.returncode != 0

    def test_git_env_sealing_targets_cwd_repo(self, tmp_path):
        """git_env → -C 语义恢复：提交落夹具仓，受害者 HEAD 不动。"""
        victim, fixture = tmp_path / "victim2", tmp_path / "fixture2"
        self._init_repo(victim)
        (victim / "seed").write_text("v", encoding="utf-8")
        self._git(victim, "add", "-A")
        self._git(victim, "commit", "-qm", "seed")
        before = self._git(victim, "rev-parse", "HEAD").stdout.strip()
        self._init_repo(fixture)
        (fixture / "factory-local.json").write_text("{}", encoding="utf-8")
        sealed = {**os.environ, "GIT_DIR": str(victim / ".git")}
        sealed = git_env(sealed)
        subprocess.run(["git", "-C", str(fixture), "add", "-A"],
                       check=True, env=sealed, capture_output=True)
        subprocess.run(["git", "-C", str(fixture), "commit", "-qm", "x"],
                       check=True, env=sealed, capture_output=True)
        assert self._git(victim, "rev-parse", "HEAD").stdout.strip() == before
        assert self._git(fixture, "rev-parse", "HEAD").stdout.strip()

    def test_git_env_strips_discovery_vars_only(self):
        env = git_env({"GIT_DIR": "/x", "GIT_WORK_TREE": "/y",
                       "PATH": "/bin", "HOME": "/u"})
        assert "GIT_DIR" not in env and "GIT_WORK_TREE" not in env
        # issue #109：PATH 纳入密闭面——base 传入值被白名单覆盖（密闭面
        # 不可被调用方松开）；其余变量（HOME）仍透传
        assert env["PATH"] == _sealed_path() and env["HOME"] == "/u"
