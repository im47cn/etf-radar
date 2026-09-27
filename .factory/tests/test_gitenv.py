"""git_env 密闭面契约测试（issue #109：宿主环境渗漏两陷阱）。

缺陷→测试映射：
- #109 陷阱①（宿主 PATH 可见 sourcery → 夹具网络闸挂起/超时）
  → test_path_whitelisted_to_anchor_dirs
- #109 陷阱②（宿主全局 gpgsign=true → 夹具 commit rc=128）
  → test_git_config_sealed_to_dev_null
- 密闭面不可被 base 松开（毒化 PATH/GIT_CONFIG_* 被覆盖）
  → test_sealed_overrides_base_poison
- PR #111 Sourcery 评论①（宿主 PATH 参与白名单推导：锚定工具与
  sourcery 同目录共存时白名单泄漏该目录）→ test_host_path_excluded
- PR #111 Sourcery 评论②（GIT_CONFIG 环境注入族优先级高于文件
  密封值，未剥除则 gpgsign 仍可注入）
  → test_git_config_injection_family_stripped
- PR #71 原契约不回归（仓库发现变量剥除）
  → test_stale_repo_discovery_stripped
- base 拷贝语义（不原地改写调用方 dict）
  → test_base_not_mutated
"""
import os
import shutil

from gitenv import _FALLBACK_DIRS, _sealed_path, git_env


def test_path_whitelisted_to_anchor_dirs():
    env = git_env()
    dirs = env["PATH"].split(os.pathsep)
    # 白名单 ⊆ 锚定目录 ∪ POSIX 标准目录（宿主私有目录整体剥除）
    allowed = {"/usr/bin", "/bin"}
    for tool in ("python3", "git", "bash"):
        if where := shutil.which(tool):
            allowed.add(os.path.dirname(where))
    assert set(dirs) <= allowed
    # 锚定工具在密闭 PATH 下仍可解析（测试链不断链）
    for tool in ("python3", "git", "bash"):
        assert shutil.which(tool, path=env["PATH"]) is not None
    # 陷阱①实证：sourcery 若在宿主 PATH 可见且不在白名单目录，
    # 密闭后必须不可见（夹具闸 command -v 跳过 → 零出网）
    sr_host = shutil.which("sourcery")
    if sr_host and os.path.dirname(sr_host) not in allowed:
        assert shutil.which("sourcery", path=env["PATH"]) is None


def test_host_path_excluded(tmp_path, monkeypatch):
    # PR #111 Sourcery 评论①：宿主 PATH 永不参与白名单推导——
    # 锚定工具与 sourcery 同目录共存的宿主形态不可再泄漏该目录
    fake = tmp_path / "hostbin"
    fake.mkdir()
    for name in ("python3", "git", "bash", "sourcery"):
        exe = fake / name
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake))
    sealed = _sealed_path()
    assert str(fake) not in sealed.split(os.pathsep)
    # POSIX 标准目录兜底不因宿主 PATH 形态而丢失（测试链不断链）
    for d in _FALLBACK_DIRS:
        assert d in sealed.split(os.pathsep)


def test_git_config_injection_family_stripped():
    # PR #111 Sourcery 评论②：GIT_CONFIG_COUNT/KEY_n/VALUE_n/
    # PARAMETERS 环境注入优先级高于 GLOBAL/SYSTEM 密封值——
    # 泄漏则 gpgsign 等仍可注入
    base = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "true",
        "GIT_CONFIG_PARAMETERS": "'commit.gpgsign=true'",
    }
    env = git_env(base)
    for k in base:
        assert k not in env
    # 剥除断面只限注入族：文件密封值照常注入
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_SYSTEM"] == "/dev/null"


def test_git_config_sealed_to_dev_null():
    # 陷阱②：宿主全局/系统 gitconfig（gpgsign 等）不渗入夹具
    env = git_env()
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_SYSTEM"] == "/dev/null"


def test_sealed_overrides_base_poison():
    # 密闭面不可被调用方松开：base 毒化 PATH/GIT_CONFIG_* 被覆盖
    env = git_env({"PATH": "/nonexistent", "GIT_CONFIG_GLOBAL": "/tmp/evil"})
    assert env["PATH"] == _sealed_path()
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_SYSTEM"] == "/dev/null"


def test_stale_repo_discovery_stripped():
    # PR #71 原契约：GIT_DIR 等仓库发现变量剥除（不回归）
    env = git_env({"GIT_DIR": "/poison", "GIT_WORK_TREE": "/poison"})
    assert "GIT_DIR" not in env
    assert "GIT_WORK_TREE" not in env


def test_base_not_mutated():
    # 拷贝语义：调用方 dict 不被原地改写
    base = {"GIT_DIR": "x"}
    git_env(base)
    assert base == {"GIT_DIR": "x"}
