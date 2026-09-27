"""R4 成本熔断接线测试 —— 门真跑 + 三入口行为接线。

三层：
1. breaker.sh 门（真 factory_lib.py breaker 子命令，无 mock）：trip /
   streak / 放行 / fail-closed（floor 缺失或损坏、ledger 行损坏）。
2. 入口行为：dispatch.sh / fix-issue.sh / cron-dispatch.sh 熔断时在任何
   gh 数据面调用、AI 节点、租约、互斥锁、下游脚本之前提前退出；未熔断
   时透传到既有下一站（dispatch 走完整轮、fix-issue 走到 gh 探测、
   cron 走到 triage+dispatch 两个哨兵）。
3. DRY 干跑：tripping 台账下也不触发熔断退出（干跑无副作用）。

沙箱模式对齐 test_fix_issue_trap：tmp git 仓 + .factory 拷贝 + PATH 桩
（gh/omp 只记录调用）；危险下游（triage-batch/factory-state）换哨兵脚本，
断言「未被触及」即证明提前退出。
运行：python3 -m pytest .factory/tests -q（conftest 注入 .factory 到 sys.path）
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path
from gitenv import git_env  # noqa: E402  (tests/ 兄弟模块，pytest rootdir 注入)

FACTORY = Path(__file__).resolve().parents[1]

# D（2026-09-05）：breaker.sh 不再固定包装"成本熔断 ledger 累计超 floor"误导
# 文案，rc=3 时透传 factory_lib breaker_check 的 CircuitOpen 真实消息
# （"熔断：今日已跑 N 次" / "熔断：连续失败 N 次…需人工介入"）。
RUNS_TRIP_MSG = "熔断：今日已跑 1 次（上限 1）"          # TRIP_FLOOR + 1 条今日成功行
STREAK_TRIP_MSG = "熔断：连续失败 3 次（上限 3），需人工介入"  # FLOOR + 3 连败
FAIL_CLOSED_MSG = "fail-closed 停止派发"
FLOOR = {"max_runs_per_day": 10, "max_consecutive_failures": 3}
TRIP_FLOOR = {"max_runs_per_day": 1, "max_consecutive_failures": 3}


def _e(exit_code: int = 0, day: str | None = None) -> str:
    """一行台账（对齐 write_ledger 的 jsonl 形态）。"""
    day = day or datetime.date.today().isoformat()
    return json.dumps({"ts": f"{day}T12:00:00Z", "issue": 1,
                       "round": 1, "type": "code", "exit": exit_code, "secs": 60})


# ---- 沙箱：tmp git 仓 + .factory 拷贝 + 哨兵下游 + PATH 桩 ----

_SENTINEL = '#!/usr/bin/env bash\necho "${0##*/}" >> "${SENTINEL_MARK:?}"\nexit 0\n'
_GH_STUB = ('#!/bin/sh\necho "gh $*" >> "${STUB_CALLS:?}"\n'
            'case "$*" in *--json*) echo "[]" ;; esac\nexit 0\n')
_OMP_STUB = '#!/bin/sh\necho "omp $*" >> "${STUB_CALLS:?}"\nexit 0\n'


def _sandbox(tmp_path: Path, floor: str | None, ledger: str | None) -> Path:
    """tmp git 仓；floor=None 不写 floor.json，ledger=None 不写 ledger.jsonl。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    env = git_env({"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"})
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    factory = repo / ".factory"
    shutil.copytree(FACTORY, factory,
                    ignore=shutil.ignore_patterns("artifacts", "worktrees", "__pycache__", "locks"))
    locks = factory / "locks"
    locks.mkdir()
    if floor is not None:
        (locks / "floor.json").write_text(floor, encoding="utf-8")
    if ledger is not None:
        (locks / "ledger.jsonl").write_text(ledger, encoding="utf-8")
    # 哨兵下游：被触及即写 SENTINEL_MARK（对齐 trap 测试「以副作用证到达」）
    for name in ("triage-batch.sh", "factory-state.sh"):
        p = factory / name
        p.write_text(_SENTINEL, encoding="utf-8")
        p.chmod(0o755)
    # gh/omp 桩：只记录调用，gh 对 --json 查询回空集
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, text in (("gh", _GH_STUB), ("omp", _OMP_STUB)):
        p = bin_ / name
        p.write_text(text, encoding="utf-8")
        p.chmod(0o755)
    return repo


def _run(cmd: list[str], repo: Path, tmp_path: Path, *, with_stubs: bool,
         extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """with_stubs=True → gh/omp 桩在前；False → 最小 PATH（无 gh，隔离真 CLI）。"""
    path = f"{tmp_path}/bin:{os.environ['PATH']}" if with_stubs else "/usr/bin:/bin"
    env = {"PATH": path, "HOME": os.environ.get("HOME", "/tmp"),
           "GH_REPO": "sandbox/repo", "SENTINEL_MARK": str(tmp_path / "sentinel"),
           "STUB_CALLS": str(tmp_path / "calls"),
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    # TZ 透传：_e() 用本进程 date.today() 写台账，breaker 子进程用其自身
    # date.today() 判「今日」——两边时区不一致时（本机 shell TZ=UTC 而系统
    # 时区 Asia/Shanghai，UTC 16:00-24:00 窗口两时区跨日）台账日期对不上，
    # 熔断误放行 rc=0（2026-09-08 实证 4 败；CI 全链 UTC 一致故绿）
    if "TZ" in os.environ:
        env["TZ"] = os.environ["TZ"]
    env |= (extra_env or {})
    return subprocess.run(cmd, cwd=repo, env=env, capture_output=True,
                          text=True, timeout=120)


def _stub_lines(tmp_path: Path) -> list[str]:
    p = tmp_path / "calls"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def _sentinel_hit(tmp_path: Path) -> list[str]:
    p = tmp_path / "sentinel"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


# ---- 1. breaker.sh 门：真跑 factory_lib breaker ----

class TestBreakerGate:
    def _gate(self, tmp_path: Path, floor: str | None, ledger: str | None):
        locks = tmp_path / "locks"
        locks.mkdir(exist_ok=True)
        if floor is not None:
            (locks / "floor.json").write_text(floor, encoding="utf-8")
        if ledger is not None:
            (locks / "ledger.jsonl").write_text(ledger, encoding="utf-8")
        return subprocess.run(["bash", str(FACTORY / "breaker.sh"), str(locks)],
                              capture_output=True, text=True, timeout=60)

    def test_daily_cap_trips_exit_3(self, tmp_path):
        r = self._gate(tmp_path, json.dumps({"max_runs_per_day": 1, "max_consecutive_failures": 3}),
                       _e(0) + "\n")
        assert r.returncode == 3
        assert RUNS_TRIP_MSG in r.stderr

    def test_streak_trips_exit_3(self, tmp_path):
        r = self._gate(tmp_path, json.dumps(FLOOR), "".join(_e(1) + "\n" for _ in range(3)))
        assert r.returncode == 3
        assert STREAK_TRIP_MSG in r.stderr
        assert "连续失败" in r.stderr  # factory_lib 判定明细先行

    def test_pass_silent_exit_0(self, tmp_path):
        r = self._gate(tmp_path, json.dumps(FLOOR), "")
        assert (r.returncode, r.stdout, r.stderr) == (0, "", "")

    def test_pass_without_ledger_file(self, tmp_path):
        """ledger 尚未生成（首跑）= 空台账，放行。"""
        r = self._gate(tmp_path, json.dumps(FLOOR), None)
        assert r.returncode == 0

    def test_missing_floor_fail_closed(self, tmp_path):
        """floor.json 缺失：不吞异常（堆栈在 stderr），fail-closed 停摆。"""
        r = self._gate(tmp_path, None, "")
        assert r.returncode == 1
        assert FAIL_CLOSED_MSG in r.stderr
        assert "Traceback" in r.stderr
        assert "floor.json" in r.stderr  # 复核指引含路径

    def test_corrupt_floor_fail_closed(self, tmp_path):
        r = self._gate(tmp_path, "{not-json", "")
        assert r.returncode == 1
        assert FAIL_CLOSED_MSG in r.stderr
        assert "Traceback" in r.stderr

    def test_corrupt_ledger_fail_closed(self, tmp_path):
        r = self._gate(tmp_path, json.dumps(FLOOR), "garbage-not-json\n")
        assert r.returncode == 1
        assert FAIL_CLOSED_MSG in r.stderr


# ---- 2. dispatch.sh：每轮派发前 ----

class TestDispatchWiring:
    def _dispatch(self, tmp_path: Path, floor: str, ledger: str, extra_env=None):
        repo = _sandbox(tmp_path, floor, ledger)
        return repo, _run(["bash", ".factory/dispatch.sh"], repo, tmp_path,
                          with_stubs=True, extra_env=extra_env)

    def test_trips_before_any_downstream(self, tmp_path):
        repo, r = self._dispatch(tmp_path, json.dumps(TRIP_FLOOR), _e(0) + "\n")
        assert r.returncode == 3
        assert RUNS_TRIP_MSG in r.stderr
        # 死在门口：无 gh 数据面调用（仅启动时的 hosting auth 探测）、无下游脚本
        gh_calls = [ln.rstrip() for ln in _stub_lines(tmp_path) if ln.startswith("gh ")]
        assert gh_calls == ["gh auth status"]  # dispatch_main 的 hosting auth 探测（ADR-008）
        assert _sentinel_hit(tmp_path) == []
        assert not (repo / ".factory/artifacts").exists()

    def test_dry_run_does_not_trip(self, tmp_path):
        _, r = self._dispatch(tmp_path, json.dumps(TRIP_FLOOR), _e(0) + "\n", extra_env={"DRY": "1"})
        assert r.returncode != 3  # 不熔断（rc=1 是既有 DRY 尾部 `[ $DRY = 0 ] && echo` 状态，非本次接线引入）
        assert "熔断" not in r.stdout + r.stderr
        assert "[dry-run]" in r.stdout  # 走的是干跑路径而非门口拦截

    def test_passes_through_full_round(self, tmp_path):
        _, r = self._dispatch(tmp_path, json.dumps(FLOOR), "")
        assert r.returncode == 0
        assert "熔断" not in r.stdout + r.stderr
        hits = _sentinel_hit(tmp_path)
        assert hits.count("triage-batch.sh") == 1
        assert hits.count("factory-state.sh") == 2  # 首尾各一次 sync --all
        assert any("pr list" in ln for ln in _stub_lines(tmp_path))  # gh 数据面已触达


    def test_auth_failure_attaches_diagnosis(self, tmp_path):
        """preflight auth 失败留痕（2026-09-05 02:00 事故）：无 gh CLI →
        exit 2 + stderr 附 auth_diagnose 诊断，日志可回溯环境/凭据归因。"""
        repo = _sandbox(tmp_path, json.dumps(FLOOR), "")
        r = _run(["bash", ".factory/dispatch.sh"], repo, tmp_path, with_stubs=False)
        assert r.returncode == 2
        assert "托管平台不可用" in r.stderr
        assert "hosting auth 诊断: gh CLI 不在 PATH" in r.stderr
        assert "熔断" not in r.stderr

# ---- 3. fix-issue.sh：AI 节点/租约/锁之前 ----

class TestFixIssueWiring:
    def _fix(self, tmp_path: Path, floor: str, ledger: str, args=None):
        repo = _sandbox(tmp_path, floor, ledger)
        return repo, _run(["bash", ".factory/fix-issue.sh"] + (args or ["99"]),
                          repo, tmp_path, with_stubs=False)

    def test_trips_before_lock_and_gh(self, tmp_path):
        repo, r = self._fix(tmp_path, json.dumps(TRIP_FLOOR), _e(0) + "\n")
        assert r.returncode == 5  # 本地映射码（3 已被锁竞争占用，见接线注释）
        assert RUNS_TRIP_MSG in r.stderr
        # 连互斥锁都未占、未到 gh 探测
        assert not (repo / ".factory/locks/dispatcher").exists()
        assert "需要 gh CLI" not in r.stderr

    def test_trip_labels_needs_human(self, tmp_path):
        """R4 落标（breaker_tripped 边）：exit 5 前 add needs-human、remove
        in-progress/triaging/accepted（add 在前：中途断裂 needs-human 也先
        可见）；全程无 remove needs-human——落标点在锁块/主 trap 安装之前，
        链死后无人剥除（时序论证见 fix-issue.sh 熔断注释块）。"""
        repo = _sandbox(tmp_path, json.dumps(TRIP_FLOOR), _e(0) + "\n")
        r = _run(["bash", ".factory/fix-issue.sh", "99"], repo, tmp_path, with_stubs=True)
        assert r.returncode == 5
        labels = [ln for ln in _stub_lines(tmp_path) if " issue edit " in ln]
        assert "--add-label factory:needs-human" in labels[0]
        for name in ("factory:in-progress", "factory:triaging", "factory:accepted"):
            assert any(f"--remove-label {name}" in ln for ln in labels), name
        assert all(
            "remove-label factory:needs-human" not in ln
            for ln in _stub_lines(tmp_path)
        )
        assert not (repo / ".factory/locks/dispatcher").exists()  # 连锁都没占

    def test_dry_run_does_not_trip(self, tmp_path):
        _, r = self._fix(tmp_path, json.dumps(TRIP_FLOOR), _e(0) + "\n", args=["99", "--dry-run"])
        assert r.returncode == 0
        assert "熔断" not in r.stdout + r.stderr
        assert "[dry-run]" in r.stdout

    def test_passes_through_to_next_stage(self, tmp_path):
        """透传证明：门口放行后走到既有下一站（沙箱无 gh → exit 2）。"""
        repo, r = self._fix(tmp_path, json.dumps(FLOOR), "")
        assert r.returncode == 2
        assert "托管平台不可用" in r.stderr
        assert "熔断" not in r.stderr
        assert not (repo / ".factory/locks/dispatcher").exists()  # trap 已放锁


# ---- 4. cron-dispatch.sh：triage 批次（dispatch 门之前）----

class TestCronDispatchWiring:
    def _cron(self, tmp_path: Path, floor: str, ledger: str):
        repo = _sandbox(tmp_path, floor, ledger)
        # dispatch 侧已有独立接线测试；此处换哨兵以证明 wrapper 两个 callee 都到/不到
        dsp = repo / ".factory/dispatch.sh"
        dsp.write_text(_SENTINEL, encoding="utf-8")
        dsp.chmod(0o755)
        return repo, _run(["/bin/sh", ".factory/cron-dispatch.sh"], repo, tmp_path,
                          with_stubs=False)

    def test_trips_before_triage_and_dispatch(self, tmp_path):
        repo, r = self._cron(tmp_path, json.dumps(TRIP_FLOOR), _e(0) + "\n")
        assert r.returncode == 3
        log = (repo / ".factory/locks/dispatch.log").read_text(encoding="utf-8")
        assert RUNS_TRIP_MSG in log  # 停摆信息随块重定向落 dispatch.log
        assert _sentinel_hit(tmp_path) == []  # triage-batch / dispatch 均未跑

    def test_passes_through_to_both_callees(self, tmp_path):
        repo, r = self._cron(tmp_path, json.dumps(FLOOR), "")
        assert r.returncode == 0
        log = (repo / ".factory/locks/dispatch.log").read_text(encoding="utf-8")
        assert "熔断" not in log
        assert sorted(_sentinel_hit(tmp_path)) == ["dispatch.sh", "triage-batch.sh"]
