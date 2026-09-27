"""dispatch 进程编排单测 —— 全部锚定 ADR-005 下沉动机（bash 进程原语缺陷类）。

缺陷→测试映射:
- jobs 表/wait 落空（0d947f60）→ TestChainPool：槽上限真并发测量（start/end
  时间戳区间重叠峰值）+ 全量收割 + 退出码可观测（bash 裸 wait 无 rc）
  + 日志目录缺省自建 + FACTORY_DISPATCHED 环境契约
- 锁原语（39b6b8ec 的 mkdir+PID 形态本体）→ TestDispatchLock：原子占 /
  陈锁接管 / 垃圾 pid 接管 / 活锁拒让 / 父目录缺省不误读
- REPO_SLUG 管道早退（a4d81930 / #30）与 heredoc 内联排序过滤（曾不可测）
  → TestDispatchParsers：纯函数直接测
"""

import os
import subprocess
import pytest
from pathlib import Path

import factory_lib
import hosting as hosting_mod
from factory_lib import (
    ChainPool,
    _DispatchCfg,
    acquire_dispatch_lock,
    approved_prs,
    dispatch_main,
    release_dispatch_lock,
    sort_by_priority,
)
extract_slug = hosting_mod.extract_slug  # ADR-008：slug 解析已迁 hosting.py

# 测试链：输出带纪元时间戳——并发峰值必须按真实时序测，按 issue 分组拼接
# 日志会抹平交错（首版测试自身的缺陷，非被测代码缺陷）
_CHAIN = """#!/usr/bin/env bash
ts() { python3 -c 'import time; print(f"{time.time():.6f}")'; }
echo "start $1 $(ts)"
sleep "${CHAIN_SLEEP:-1}"
echo "end $1 $(ts)"
exit "${CHAIN_RC:-0}"
"""


def _factory_with_chain(tmp_path: Path) -> Path:
    f = tmp_path / "factory"
    f.mkdir()
    p = f / "fix-issue.sh"
    p.write_text(_CHAIN, encoding="utf-8")
    p.chmod(0o755)
    return f


def _lines(factory: Path, issue: int) -> list[str]:
    log = factory / "artifacts" / f"issue-{issue}" / "dispatch.log"
    return [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln]

def _peak_concurrency(marks: list[tuple[float, int]]) -> int:
    """按 start/end 时间戳区间的重叠峰值（并发上界测量）。"""
    running = peak = 0
    for _, delta in sorted(marks):
        running += delta
        peak = max(peak, running)
    return peak


class TestChainPool:
    def test_max_parallel_respected_and_all_ran(self, tmp_path):
        """MAX=2 派 5 链：按 start/end 时间戳区间算重叠峰值恰为 2
        （`jobs -rp | wc -l` 清点竞态在 Popen 句柄模型下不可表达），
        5 链全部跑完且各留下成对边界。"""
        f = _factory_with_chain(tmp_path)
        pool = ChainPool(f, max_parallel=2, poll_secs=0.05)
        for n in (1, 2, 3, 4, 5):
            pool.spawn(n)
        pool.wait_all()
        marks = []
        for n in range(1, 6):
            lines = _lines(f, n)
            assert len(lines) == 2 and lines[0].startswith("start") \
                    and lines[1].startswith("end"), f"issue-{n} 链未完整跑完: {lines}"
            marks.extend(
                ((float(lines[0].split()[2]), 1), (float(lines[1].split()[2]), -1))
            )
        assert _peak_concurrency(marks) == 2

    def test_wait_all_collects_exit_codes(self, tmp_path, monkeypatch):
        """bash 轮末裸 wait 无退出码 → done 收割 (issue, rc) 链路失败可观测。"""
        f = _factory_with_chain(tmp_path)
        monkeypatch.setenv("CHAIN_RC", "7")
        monkeypatch.setenv("CHAIN_SLEEP", "0")
        pool = ChainPool(f, max_parallel=2, poll_secs=0.05)
        pool.spawn(3)
        pool.wait_all()
        assert pool.done == [(3, 7)]

    def test_dispatch_log_appended_and_dir_autocreated(self, tmp_path, monkeypatch):
        """链输出尾追 artifacts/issue-N/dispatch.log；父目录缺省自建——
        bash `>>` 对缺目录静默死链（链从未起跑）的形态修复。"""
        f = _factory_with_chain(tmp_path)
        monkeypatch.setenv("CHAIN_SLEEP", "0")
        pool = ChainPool(f, max_parallel=1, poll_secs=0.05)
        pool.spawn(9)
        pool.wait_all()
        pool.spawn(9)
        pool.wait_all()
        assert len([ln for ln in _lines(f, 9)
                    if ln.startswith("start 9")]) == 2

    def test_spawn_env_marks_dispatched(self, tmp_path, monkeypatch):
        """FACTORY_DISPATCHED=1 必须进链环境（fix-issue 据此免获取手动互斥
        锁，防自锁——bash 版契约）。"""
        seen = {}

        def fake_popen(cmd, **kw):
            seen["env"] = kw.get("env")

            class _P:
                def poll(self):
                    return 0

                returncode = 0
            return _P()

        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        pool = ChainPool(tmp_path, max_parallel=2, poll_secs=0.05)
        pool.spawn(1)
        pool.wait_all()
        assert seen["env"]["FACTORY_DISPATCHED"] == "1"


class TestDispatchLock:
    def test_first_acquire_wins_live_holder_refuses(self, tmp_path):
        lock = tmp_path / "locks" / "dispatcher"
        assert acquire_dispatch_lock(lock, os.getpid()) is True
        assert acquire_dispatch_lock(lock, os.getpid()) is False  # 活持有者：拒让
        release_dispatch_lock(lock)
        assert acquire_dispatch_lock(lock, os.getpid()) is True  # 放锁后可再占

    def test_stale_pid_takeover(self, tmp_path):
        """持有者已死 → 接管陈锁（PID 活性检测的意义所在）。"""
        lock = tmp_path / "locks" / "dispatcher"
        p = subprocess.Popen(["sleep", "5"])
        p.terminate()
        p.wait()
        lock.mkdir(parents=True)
        (lock / "pid").write_text(str(p.pid), encoding="ascii")
        assert acquire_dispatch_lock(lock, os.getpid()) is True

    def test_garbage_pid_takeover(self, tmp_path):
        """垃圾 pid 文件 → kill -0 报错语义 → 按死接管（bash 同参）。"""
        lock = tmp_path / "locks" / "dispatcher"
        lock.mkdir(parents=True)
        (lock / "pid").write_text("not-a-pid", encoding="ascii")
        assert acquire_dispatch_lock(lock, os.getpid()) is True

    def test_empty_pid_file_means_busy(self, tmp_path):
        """mkdir 在而 pid 空：无法判定持有者死活，按忙退出（bash 同参：
        `[ -n "$pid" ]` 假 → 不接管）。"""
        lock = tmp_path / "locks" / "dispatcher"
        lock.mkdir(parents=True)
        (lock / "pid").write_text("", encoding="ascii")
        assert acquire_dispatch_lock(lock, os.getpid()) is False

    def test_missing_parent_not_misread_as_locked(self, tmp_path):
        """父目录不存在 → 自建（etf-radar PR#79：ENOENT 误读为锁被持而静默
        退出）。"""
        lock = tmp_path / "a" / "b" / "locks" / "dispatcher"
        assert acquire_dispatch_lock(lock, os.getpid()) is True

    def test_release_is_idempotent(self, tmp_path):
        lock = tmp_path / "locks" / "dispatcher"
        release_dispatch_lock(lock)  # 不存在也放：不抛
        acquire_dispatch_lock(lock, os.getpid())
        release_dispatch_lock(lock)
        release_dispatch_lock(lock)


class TestDispatchParsers:
    def test_sort_by_priority_full_ladder(self):
        issues = [
            {"number": 7, "labels": ["factory:accepted"]},
            {"number": 2, "labels": ["priority:low"]},
            {"number": 5, "labels": ["priority:critical"]},
            {"number": 3, "labels": ["priority:medium", "x"]},
            {"number": 4, "labels": ["priority:high"]},
        ]
        assert sort_by_priority(issues) == [5, 4, 3, 2, 7]

    def test_sort_by_priority_tie_by_number_and_empty_labels(self):
        issues = [
            {"number": 9, "labels": ["priority:high"]},
            {"number": 8, "labels": []},
            {"number": 6, "labels": ["priority:high"]},
        ]
        assert sort_by_priority(issues) == [6, 9, 8]

    def test_approved_prs_filters_review_decision(self):
        prs = [
            {"number": 1, "mergeable": True, "review": "approved"},
            {"number": 2, "mergeable": True, "review": "changes_requested"},
            {"number": 3, "mergeable": False, "review": "approved"},
        ]
        assert approved_prs(prs) == [(1, True), (3, False)]

    def test_extract_slug_shapes(self):
        assert extract_slug(["git@github.com:owner/repo.git"]) == "owner/repo"
        assert extract_slug(["https://github.com/owner/repo"]) == "owner/repo"
        assert extract_slug(["ssh://git@github.com:443/owner/repo.git"]) == "owner/repo"
        assert extract_slug(["git@gitlab.com:a/b.git"]) == ""

    def test_extract_slug_first_github_wins(self):
        # github remote 行序在前（resolve_repo_slug 注入顺序保证），首条胜出
        assert extract_slug(["https://github.com/a/one.git",
                             "https://github.com/b/two.git"]) == "a/one"
        assert extract_slug(["git@gitlab.com:a/b.git",
                             "https://github.com/o/r.git"]) == "o/r"

    def test_extract_slug_ssh_dot_github_host(self):
        """ssh.github.com 是 GitHub 官方 443 端口 SSH 端点（insteadOf 改写后
        git remote get-url --push 的真实产出形态）。2026-08-25 回归：a7d52b7d
        加固只认 github.com，本形态被误拒 → dispatch 全形态 exit 2 停摆。"""
        assert extract_slug(
            ["ssh://git@ssh.github.com:443/im47cn/awesome-rules.git"]
        ) == "im47cn/awesome-rules"
        assert extract_slug(["ssh://ssh.github.com/o/r.git"]) == "o/r"
    def test_extract_slug_extra_host_env(self, monkeypatch):
        """ADR-012：bot ssh Host 别名是机器事实配置（~/.ssh/config），
        经 FACTORY_SLUG_EXTRA_HOSTS 注入白名单（env 两级回退，与 PR #61
        平台配置同模式）——公开仓零内部标识。2026-09-01 回归保真：别名
        URL 未被认曾致 dispatch exit 2 停摆，故配置注入路径必须有测。"""
        monkeypatch.setenv("FACTORY_SLUG_EXTRA_HOSTS", "ci-bot-host")
        assert extract_slug(
            ["git@ci-bot-host:some-org/xx-go-sdk.git"]
        ) == "some-org/xx-go-sdk"
        # 未配置时同 host 被拒：主机锚定防伪装语义不因配置缺省放宽
        monkeypatch.delenv("FACTORY_SLUG_EXTRA_HOSTS")
        assert extract_slug(["git@ci-bot-host:some-org/xx-go-sdk.git"]) == ""
        # 近似 host 不放宽（ci-bot-host.com 非 ehost.com）
        monkeypatch.setenv("FACTORY_SLUG_EXTRA_HOSTS", "ehost.com")
        assert extract_slug(["git@ehost.com.evil.io:o/r.git"]) == ""
        # 非法 token（regex 注入面）fail-closed 抛错而非静默降级
        monkeypatch.setenv("FACTORY_SLUG_EXTRA_HOSTS", "a(b")
        with pytest.raises(ValueError):
            extract_slug(["git@github.com:o/r.git"])

    def test_extract_slug_codeup_rejected(self):
        """Codeup（阿里云效）URL 不匹配 GitHub 锚定：未接入仓 fail-closed
        空串，不得误解析为 GitHub slug（ADR-008 平台隔离）。"""
        assert extract_slug(
            ["git@codeup.aliyun.com:610b3c9d86508f8da8b08436/gtsp/x.git"]
        ) == ""

    def test_extract_slug_spoof_hosts_rejected(self):
        """伪装主机负控制：权威主机锚定后以 [/:] 定界，子串/后缀伪装全拒。"""
        assert extract_slug(["https://evil.com/github.com/o/r"]) == ""
        assert extract_slug(["ssh://git@github.com.evil.com:22/o/r.git"]) == ""
        assert extract_slug(["ssh://git@ssh.github.com.evil.com:443/o/r.git"]) == ""
        assert extract_slug(["https://ssh.github.com.evil.com/o/r"]) == ""
        assert extract_slug(["git@notssh.github.com:o/r.git"]) == ""

    def test_codeup_remote_derivation(self, monkeypatch):
        """CodeupAdapter._remote 双形态推导（PR #112 Sourcery 评论②）：
        https:// 与 SSH/scp 等价解析 org/ns/repo；解析失败 (None, None)。"""
        from types import SimpleNamespace

        a = hosting_mod.CodeupAdapter(repo=".")
        cases = [
            ("https://codeup.aliyun.com/6ab/gtsp/x.git", ("6ab", "gtsp/x")),
            ("https://codeup.aliyun.com/6ab/gtsp/x", ("6ab", "gtsp/x")),
            ("ssh://git@codeup.aliyun.com:22/6ab/gtsp/x.git", ("6ab", "gtsp/x")),
            ("git@codeup.aliyun.com:6ab/gtsp/x.git", ("6ab", "gtsp/x")),
            ("https://codeup.aliyun.com/only-org", (None, None)),
        ]
        for url, want in cases:
            monkeypatch.setattr(
                hosting_mod.subprocess, "run",
                lambda *args, **kw: SimpleNamespace(stdout=url + "\n", returncode=0))
            assert a._remote() == want, url

    def test_detect_hosting_host_anchor(self, monkeypatch):
        """codeup 域名精确锚定（CodeQL：子串匹配可被 URL 任意位置伪造）：
        后缀伪装/路径含域名形态全拒。"""
        from types import SimpleNamespace

        monkeypatch.delenv("FACTORY_HOSTING", raising=False)

        def detect(url):
            monkeypatch.setattr(
                hosting_mod.subprocess, "run",
                lambda *args, **kw: SimpleNamespace(stdout=url + "\n", returncode=0))
            return hosting_mod._detect_hosting(".")

        assert detect("https://codeup.aliyun.com/6ab/gtsp/x.git") == "codeup"
        assert detect("git@codeup.aliyun.com:6ab/gtsp/x.git") == "codeup"
        assert detect("https://codeup.aliyun.com.evil.com/6ab/x.git") == "github"
        assert detect("https://evil.com/codeup.aliyun.com/6ab/x.git") == "github"
        assert detect("https://github.com/o/r.git") == "github"
        assert detect("") == "github"

class TestDispatchConfig:
    """MAX_PARALLEL 配置错误必须 fail-fast（PR #53 审查②）：0/负/非整数
    使 ChainPool 槽满等待永真——挂起而非配置错误。config-error = rc 2。"""

    def test_chain_pool_rejects_nonpositive(self, tmp_path):
        with pytest.raises(ValueError):
            ChainPool(tmp_path, 0)
        with pytest.raises(ValueError):
            ChainPool(tmp_path, -1)

    def test_max_parallel_zero_is_config_error(self, monkeypatch, capsys):
        monkeypatch.setenv("MAX_PARALLEL", "0")
        assert dispatch_main([]) == 2
        assert "MAX_PARALLEL" in capsys.readouterr().err

    def test_max_parallel_garbage_is_config_error(self, monkeypatch, capsys):
        monkeypatch.setenv("MAX_PARALLEL", "abc")
        assert dispatch_main([]) == 2
        assert "MAX_PARALLEL" in capsys.readouterr().err


class TestChainPoolShutdown:
    """TERM 出口收尸（PR #53 审查④）：孤儿链在锁释放后仍跑会与新
    dispatcher 并发——shutdown 必须 SIGTERM → 限期收割 → SIGKILL 兜底，
    且先于放锁完成。"""

    def test_shutdown_terminates_and_reaps_active(self, tmp_path):
        f = tmp_path / "factory"
        (f / "artifacts").mkdir(parents=True)
        (f / "fix-issue.sh").write_text("#!/usr/bin/env bash\nsleep 60\n")
        (f / "fix-issue.sh").chmod(0o755)
        pool = ChainPool(f, 2, poll_secs=0.05)
        pool.spawn(7)
        assert pool._active, "链应在跑"
        stuck = pool.shutdown(grace=1.0)
        assert stuck == []
        assert pool._active == []
        assert [n for n, _ in pool.done] == [7]
        assert pool.done[0][1] != 0, "被终止的链退出码必须非 0（信号）"

    def test_shutdown_empty_pool_is_noop(self, tmp_path):
        assert ChainPool(tmp_path, 1).shutdown() == []


class TestHostingJson:
    """_hosting_json 失败可见（PR #53 审查⑤ 同源）：HostingError 必须有
    stderr 告警 + 空列表降级——静默空轮 = 整轮空转还报成功。"""

    def test_hosting_error_warns_and_skips(self, tmp_path, monkeypatch, capsys):
        def boom():
            raise hosting_mod.HostingError("pr list 失败: HTTP 502")
        cfg = _DispatchCfg(tmp_path, tmp_path, None, True)
        assert factory_lib._hosting_json(cfg, "pr list", boom) == []
        err = capsys.readouterr().err
        assert "pr list" in err and "跳过该批" in err

    def test_ok_passthrough(self, tmp_path):
        cfg = _DispatchCfg(tmp_path, tmp_path, None, True)
        assert factory_lib._hosting_json(cfg, "x", lambda: [1, 2]) == [1, 2]
