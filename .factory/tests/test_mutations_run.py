"""mutations/run.py 单测 —— 判定（judge）与配置校验（load_defects）的退出码
语义 + run_gate 超时杀组的进程组生命周期行为。

judge/load_defects 锁纯函数契约（不跑外部进程）。run_gate 超时路径
（test_timeout_* 系列）例外：启动真实 bash 子进程组并断言其被杀透——
平台敏感（macOS XNU 僵尸窗口 EPERM 语义，见 PR #36）。
testing-standards「退出码语义」：0=放行、1=击杀证据；其他退出码/超时
一律无效运行，既不奖励击杀也不奖励放行。
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mutations"))

import run as mut  # noqa: E402


def _defect(**kw) -> mut.Defect:
    base = (
        dict(
            id="X-01",
            description="d",
            target="t",
            find="f",
            replace="r",
            gate="guard",
            expect_block=True,
        )
        | kw
    )
    return mut.Defect(**base)


class TestJudge:
    """退出码 → PASS/FAIL 判定表。"""

    def test_blocked_positive_pass(self):
        assert mut.judge(_defect(gate="guard", expect_block=True), 1)[0] == "PASS"

    def test_released_negative_pass(self):
        assert mut.judge(_defect(gate="guard", expect_block=False), 0)[0] == "PASS"

    def test_survived_mutation_fail(self):
        status, detail = mut.judge(_defect(gate="guard"), 0)
        assert status == "FAIL"
        assert "expect_block" in detail

    def test_blocked_negative_fail(self):
        assert mut.judge(_defect(gate="guard", expect_block=False), 1)[0] == "FAIL"

    def test_guard_fail_closed_rc2_counts_as_block(self):
        """guard rc=2 = fail-closed（门崩溃=拦截，G-03 语义），正例 PASS。"""
        assert mut.judge(_defect(gate="guard", expect_block=True), 2)[0] == "PASS"

    @pytest.mark.parametrize("expect_block", [True, False])
    def test_timeout_is_invalid_run_for_both_polarities(self, expect_block):
        """超时（rc=None）：正例不奖励击杀、负例不奖励放行。"""
        status, detail = mut.judge(_defect(gate="tests", expect_block=expect_block), None)
        assert status == "FAIL"
        assert "无效运行" in detail

    @pytest.mark.parametrize("rc", [2, 127])
    def test_tests_gate_rc_out_of_domain_invalid(self, rc):
        """run_tests.sh 退出码域为 0/1；域外 = 无效运行而非击杀。"""
        status, detail = mut.judge(_defect(gate="tests", expect_block=True), rc)
        assert status == "FAIL"
        assert "无效退出码" in detail


class TestLoadDefects:
    """配置校验：id 唯一、gate 枚举闭合。"""

    @staticmethod
    def _write(tmp_path: Path, defects: list[dict]) -> Path:
        p = tmp_path / "defects.json"
        p.write_text(json.dumps({"defects": defects}, ensure_ascii=False),
                     encoding="utf-8")
        return p

    def test_duplicate_id_rejected(self, tmp_path):
        p = self._write(tmp_path, [asdict(_defect(id="D-1")), asdict(_defect(id="D-1"))])
        with pytest.raises(ValueError, match="重复"):
            mut.load_defects(p)

    def test_unknown_gate_rejected(self, tmp_path):
        p = self._write(tmp_path, [asdict(_defect(gate="lint"))])
        with pytest.raises(ValueError, match="未知 gate"):
            mut.load_defects(p)

    def test_both_gates_accepted(self, tmp_path):
        p = self._write(tmp_path, [asdict(_defect(gate="guard")),
                                   asdict(_defect(id="X-2", gate="tests"))])
        assert len(mut.load_defects(p)) == 2

def _assert_group_dead(pgid: int, *, timeout: float = 10.0) -> None:
    """探活直到进程组消失（跨平台僵尸语义安全）。

    EPERM = 组内仅剩待-reap 僵尸（macOS XNU 对含僵尸的组发信号报
    EPERM，同 UID 亦然；真活进程不会）——活进程已被杀，等 init 收尸
    后复探。ESRCH = 组彻底消失。探活成功（rc=0）仅表示信号调用成功、
    组仍有成员——Linux 上未收尸僵尸同样探活成功，不据此断言真活
    （区分真活/僵尸须用显式子进程状态，此处不需要：等待组消失本身
    即断言语义）。组未在 deadline 内消失才判失败。
    """
    import os
    import time as _time
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)                   # 探活：组内是否仍有成员
        except ProcessLookupError:
            return                               # 组彻底消失（含 sleep 孙进程）
        except PermissionError:
            pass                                 # 仅剩待-reap 僵尸，复探等收尸
        _time.sleep(0.05)
    pytest.fail(f"进程组 {pgid} 在 {timeout}s 后未消失（仍有成员）")

def _slow_gate(tmp_path):
    """夹具门：派生 sleep 孙进程后挂起（组内有真活成员，只杀 leader
    会留孤儿，断言才有杀组语义面）。"""
    gate = tmp_path / "slow_gate.sh"
    gate.write_text("#!/bin/bash\nsleep 60 &\nwait\n", encoding="utf-8")
    gate.chmod(0o755)
    return gate


def _capture_gate_pgid(monkeypatch):
    """从派生侧捕获门的 pgid：start_new_session 下 pgid == Popen pid
    （run.py 同一不变式）。刻意不做门内 echo $$ > 文件握手——xdist 多
    worker 负载下 bash 启动可晚于 1s 超时杀组，文件永不落盘（2026-09-20
    实证 FileNotFoundError）。"""
    real_popen = mut.subprocess.Popen
    captured = []

    def _popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        captured.append(proc.pid)
        return proc

    monkeypatch.setattr(mut.subprocess, "Popen", _popen)
    return captured


def test_timeout_kills_process_group(tmp_path, monkeypatch):
    """超时杀整个进程组（PR #33 审查）：只杀 bash 直子会留孤儿继续读
    注入中的 target，还原窗口被污染。夹具门派生 sleep 孙进程后挂起；
    断言超时后整组无存活（pgid 取自 Popen 派生侧，见 _capture_gate_pgid）。"""
    gate = _slow_gate(tmp_path)
    pgids = _capture_gate_pgid(monkeypatch)
    monkeypatch.setattr(mut, "FINAL_GATE", [str(gate)])
    monkeypatch.setattr(mut, "TESTS_TIMEOUT", 1)
    assert mut.run_gate("tests", "whatever") is None
    _assert_group_dead(pgids[0])



def test_timeout_sigkill_eperm_tolerated(tmp_path, monkeypatch):
    """run_gate 超时杀组遇 killpg(SIGKILL)=EPERM（macOS 组内仅剩待-reap
    僵尸）→ 容忍而非炸掉调用方，仍返回 None（无效运行语义不变），
    且组确已死透。"""
    import errno
    import os
    import signal
    gate = _slow_gate(tmp_path)
    pgids = _capture_gate_pgid(monkeypatch)
    real_killpg = os.killpg

    def killpg_then_eperm(pgid, sig):
        real_killpg(pgid, sig)              # 真杀，避免组残留污染用例
        if sig == signal.SIGKILL:
            raise PermissionError(errno.EPERM, "zombie-only pgroup")

    monkeypatch.setattr(os, "killpg", killpg_then_eperm)
    monkeypatch.setattr(mut, "FINAL_GATE", [str(gate)])
    monkeypatch.setattr(mut, "TESTS_TIMEOUT", 1)
    assert mut.run_gate("tests", "whatever") is None
    _assert_group_dead(pgids[0])


def test_probe_tolerates_macos_zombie_window(monkeypatch):
    """杀组断言的确定性规格（flake 回归锁）：探活序列 EPERM→EPERM→ESRCH
    ⟹ 通过——EPERM 即组内仅剩待-reap 僵尸，活进程已被杀。真实僵尸窗口
    依赖 launchd 收尸时序无法稳定复现，故 mock os.killpg 探活路径
    （sig==0），SIGKILL 等真实信号透传。"""
    import errno
    import os
    real_killpg = os.killpg
    probes = iter((PermissionError(errno.EPERM, "zombie"),
                   PermissionError(errno.EPERM, "zombie"),
                   ProcessLookupError(errno.ESRCH, "gone")))

    def fake_killpg(pgid, sig):
        if sig == 0:
            raise next(probes)
        real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", fake_killpg)
    _assert_group_dead(4242)                     # 走完序列 → ESRCH → 通过


def test_probe_fails_when_group_still_alive(monkeypatch):
    """负例：探活持续成功（组内真有活成员，杀组失效）→ deadline 后
    判失败，而非误判通过。"""
    import os
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: None)
    with pytest.raises(pytest.fail.Exception, match="未消失"):
        _assert_group_dead(4242, timeout=0.2)


class TestFinalGateWords:
    """final_gate_cmd 加载（PR #71 Sourcery #2：类型校验 fail-closed）。"""

    @pytest.mark.parametrize("bad_val", [123, ["uv", "run"], {"cmd": "x"}, True])
    def test_non_string_fails_closed(self, tmp_path, bad_val):
        """非字符串 JSON 值（数字/列表/对象/布尔）→ RuntimeError，
        与 factory_lib._local_str 同规——str() 静默转换会让 py 侧放行
        而 shell 侧拒绝，两消费方行为必须一致。"""
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"final_gate_cmd": bad_val}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="final_gate_cmd"):
            mut._final_gate_words(cfg)

    def test_valid_path_style_splits(self, tmp_path):
        """PATH 型命令拆词保持原样（首词不被绝对化/不加 bash）。"""
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(
            json.dumps({"final_gate_cmd": "uv run pytest -q"}), encoding="utf-8")
        assert mut._final_gate_words(cfg) == ["uv", "run", "pytest", "-q"]

    @pytest.mark.parametrize("bad_val", ["a\nb", "a\rb", "a\n"])
    def test_newline_fails_closed(self, tmp_path, bad_val):
        """禁含换行（PR #110 Sourcery 追评收口）：read -r -a 只取
        here-string 首行、shlex 多行拆词——含换行配置两侧 argv 分歧，
        与 factory_lib 侧同禁。首尾换行负例锁校验位于 strip 前
        （任何位置换行即拒，与 _local_str 返回原值不 strip 镜像）。"""
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"final_gate_cmd": bad_val}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="final_gate_cmd"):
            mut._final_gate_words(cfg)


def test_run_gate_executes_final_gate_without_bash_prefix(monkeypatch):
    """tests 门直执 FINAL_GATE（PR #71 Sourcery #1）：bash 前缀会把
    PATH 型首词（如 uv）当脚本文件名，门必失败；直执与 shell 侧
    fix-issue/validate-pr 的 "${GATE_ARGS[@]}" 同构。"""
    seen = {}

    class _Proc:
        returncode = 0
        pid = -1

        def communicate(self, timeout=None):
            return ("", "")

    def fake_popen(cmd, **kw):
        seen["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(mut, "FINAL_GATE", ["uv", "run", "pytest"])
    monkeypatch.setattr(mut.subprocess, "Popen", fake_popen)
    rc = mut.run_gate("tests", "some_target.py")
    assert rc == 0
    assert seen["cmd"] == ["uv", "run", "pytest"]


class TestFinalGateDriftLock:
    """final_gate_cmd 双实现漂移锁（ADR-010）。

    shell 侧（fix-issue/validate-pr：factory_lib.final-gate 输出 +
    read -r -a 拆词）与 python 侧（mutations：_final_gate_words +
    shlex.split）是两套实现、两个拆词器——PR #71 Sourcery S1 的 bash
    前缀漂移即双实现产物。保留 python 实现的决策下，一致性必须机械化。
    拆词器分叉点闭集：引号（shlex 剥除 / read 字面）、反斜杠（shlex
    转义 / read -r 字面）与换行（read -r -a 只取首行 / shlex 多行拆
    词）——双侧校验同禁后，纯空白分隔下两拆词器逐词
    相等；活配置单一事实源断言锁住「两侧永远消费同一字符串」。
    """

    @pytest.mark.parametrize("cmd", [
        "scripts/run_tests.sh --no-lock",          # 仓相对脚本（本仓形态）
        "uv run pytest -q",                        # PATH 型（Sourcery S1 场景）
        "pytest .factory -q --timeout=600",        # 多词 + =值
    ])
    def test_shell_and_python_splitters_agree(self, tmp_path, cmd):
        """同一配置双侧拆词逐词相等：shell 侧语义 = final_gate_cmd() 原文
        + read -ra（bash read -ra 按 IFS 空白拆词、不做引号解释）；python
        侧 = _final_gate_words（shlex；禁引号约束下与空白拆词等价）。"""
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"final_gate_cmd": cmd}), encoding="utf-8")
        assert mut._final_gate_words(cfg) == cmd.split()

    def test_live_config_single_source(self):
        """两侧消费同一 factory-local.json：python FINAL_GATE 必须等于
        factory_lib.final_gate_cmd() 的 read -ra 拆词（活配置漂移即红）。"""
        import factory_lib
        live = factory_lib.final_gate_cmd()
        assert mut.FINAL_GATE == live.split()

    def test_rejects_divergent_quote_policy(self, tmp_path):
        """引号策略分叉锁：任一侧放宽引号拒绝，拆词器差异即产生 argv
        分叉——双侧拒绝规则必须同时存在（final_gate_cmd 与
        _final_gate_words 的引号校验互为镜像）。"""
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"final_gate_cmd": 'sh -c "x"'}),
                       encoding="utf-8")
        with pytest.raises(RuntimeError):
            mut._final_gate_words(cfg)          # python 侧拒绝
        import factory_lib
        orig = factory_lib._LOCAL_CFG
        try:
            factory_lib._LOCAL_CFG = {"final_gate_cmd": 'sh -c "x"'}
            with pytest.raises(RuntimeError):
                factory_lib.final_gate_cmd()    # shell 供词侧同拒
        finally:
            factory_lib._LOCAL_CFG = orig

    @pytest.mark.parametrize("bad", ["a\\ b", "x\\y", "tail\\"])
    def test_rejects_backslash_divergence(self, tmp_path, bad):
        """反斜杠分叉锁（ADR-010）：shlex 把反斜杠当转义（`a\\ b` → 1 词
        `a b`）、read -r -a 当字面（→ 2 词 `a\\` / `b`）——词数即不同，
        且旧校验（仅禁引号）双侧都放行。双侧同拒后「过校验 ⇒ 两侧拆词
        逐词一致」不变量才闭环。"""
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"final_gate_cmd": bad}), encoding="utf-8")
        with pytest.raises(RuntimeError):
            mut._final_gate_words(cfg)
        import factory_lib
        orig = factory_lib._LOCAL_CFG
        try:
            factory_lib._LOCAL_CFG = {"final_gate_cmd": bad}
            with pytest.raises(RuntimeError):
                factory_lib.final_gate_cmd()
        finally:
            factory_lib._LOCAL_CFG = orig

    @pytest.mark.parametrize("bad", ["a\nb", "a\rb", "a\n"])
    def test_rejects_newline_divergence(self, tmp_path, bad):
        """换行分叉锁（PR #110 Sourcery 追评收口）：read -r -a 只取
        here-string 首行、shlex 多行拆词——词数即不同，且旧校验（禁
        引号+反斜杠）双侧都放行。双侧同禁后「过校验 ⇒ 两侧拆词逐词
        一致」不变量对换行同样闭环。"""
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"final_gate_cmd": bad}), encoding="utf-8")
        with pytest.raises(RuntimeError):
            mut._final_gate_words(cfg)          # python 侧拒绝
        import factory_lib
        orig = factory_lib._LOCAL_CFG
        try:
            factory_lib._LOCAL_CFG = {"final_gate_cmd": bad}
            with pytest.raises(RuntimeError):
                factory_lib.final_gate_cmd()    # shell 供词侧同拒
        finally:
            factory_lib._LOCAL_CFG = orig


class TestDocstringGateWords:
    """docstring_gate_cmd 加载（2026-08-31 可选门）：键缺失 → None；
    键存在 → 与 final_gate_cmd 同规（非空字符串 + 禁引号/反斜杠/换行）。"""

    def test_missing_key_returns_none(self, tmp_path):
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"final_gate_cmd": "x"}), encoding="utf-8")
        assert mut._docstring_gate_words(cfg) is None

    def test_valid_command_splits(self, tmp_path):
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"docstring_gate_cmd": "scripts/docstring_gate.py"}),
                       encoding="utf-8")
        assert mut._docstring_gate_words(cfg) == ["scripts/docstring_gate.py"]

    @pytest.mark.parametrize("bad_val", [123, ["a"], True, ""])
    def test_non_string_or_empty_fails_closed(self, tmp_path, bad_val):
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"docstring_gate_cmd": bad_val}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="docstring_gate_cmd"):
            mut._docstring_gate_words(cfg)

    def test_quote_or_backslash_fails_closed(self, tmp_path):
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"docstring_gate_cmd": 'sh -c "x"'}),
                       encoding="utf-8")
        with pytest.raises(RuntimeError, match="docstring_gate_cmd"):
            mut._docstring_gate_words(cfg)

    @pytest.mark.parametrize("bad_val", ["a\nb", "a\rb", "a\n"])
    def test_newline_fails_closed(self, tmp_path, bad_val):
        """禁含换行（与 _final_gate_words/factory_lib 侧同禁，PR #110
        Sourcery 追评收口）。"""
        cfg = tmp_path / "factory-local.json"
        cfg.write_text(json.dumps({"docstring_gate_cmd": bad_val}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="docstring_gate_cmd"):
            mut._docstring_gate_words(cfg)


class TestDocstringGateJudge:
    """docstring 门退出码域 {0,1}（与 tests 同规）：rc=2/超时 = 无效运行 FAIL。"""

    def _def(self, expect_block):
        return mut.Defect("D-01", "d", "t", "f", "r", "docstring", expect_block)

    def test_rc1_blocks(self):
        assert mut.judge(self._def(True), 1) == ("PASS", "blocked=True（rc=1）符合预期")

    def test_rc0_passes_negative(self):
        assert mut.judge(self._def(False), 0) == ("PASS", "blocked=False（rc=0）符合预期")

    def test_rc2_invalid_run(self):
        verdict, detail = mut.judge(self._def(True), 2)
        assert verdict == "FAIL" and "无效退出码" in detail

    def test_timeout_invalid_run(self):
        verdict, _ = mut.judge(self._def(True), None)
        assert verdict == "FAIL"


class TestMainSmoke:
    """main() CLI 入口冒烟（2026-08-31 事故锚）。

    三方合并曾吞掉 _process_defect/_check_restored 的函数头（函数体悬空在
    _load_and_filter 内，main() 一调即 NameError），当时 302 测试全绿掩盖了
    它——main 属 CLI 入口，不在任何单测触达面。本冒烟固化入口契约：
    argparse 解析 → 过滤 → 汇总 → 判定全链路不炸，退出码语义正确。
    """

    def test_main_only_nonexistent_id_config_error(self, monkeypatch, capsys):
        """--only 含未知 id → 配置错误 rc 2（下游 xx-web-tools 反哺：过滤空
        清单以 0 退出写戳 = 配置错误伪装成全量验证；rc 2 对齐 guard 用法错误
        语义。原 exit0 断言固化的正是此缺陷，已翻转）。"""
        monkeypatch.setattr(mut, "write_stamp", lambda *a, **k: None)  # 不动 evidence-stamp
        monkeypatch.setattr(sys, "argv", ["run.py", "--only", "X-nonexistent"])
        rc = mut.main()
        assert rc == 2
        assert "未知缺陷 id" in capsys.readouterr().err

    def test_main_target_outside_repo_fails_config(self, monkeypatch, capsys, tmp_path):
        """target 越出 REPO_ROOT（`..` 与绝对路径）→ FAIL-config → rc 1
        （下游 xx-web-tools 反哺：--defects 载外部 JSON 时 `..` 可指向仓外
        文件注入+写回，进程非正常终止 = 注入残留落仓外）。"""
        for target in ("../escape-probe-918273", str(tmp_path / "outside-918273")):
            cfg = {"defects": [{
                "id": "T-99", "description": "越仓探针", "target": target,
                "find": "不可能存在的锚点 918273", "replace": "x",
                "gate": "guard", "expect_block": True,
            }]}
            p = tmp_path / "defects-probe.json"
            p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            monkeypatch.setattr(mut, "write_stamp", lambda *a, **k: None)
            monkeypatch.setattr(sys, "argv", ["run.py", "--defects", str(p)])
            rc = mut.main()
            assert rc == 1
            assert "越出仓库根" in capsys.readouterr().out

    def test_main_missing_defects_file_raises(self, monkeypatch, tmp_path):
        """--defects 指向缺失文件 → FileNotFoundError 传播（fail-fast，无静默空跑）。"""
        monkeypatch.setattr(sys, "argv", ["run.py", "--defects", str(tmp_path / "nope.json")])
        with pytest.raises(FileNotFoundError):
            mut.main()

    def test_write_stamp_glob_latest_evidence(self, tmp_path, monkeypatch):
        """write_stamp() 缺省取 mutations/ 目录最新 EVIDENCE-*.md（下游
        xx-web-tools 反哺：静态默认文件名会过期，写戳引用不存在的留档 =
        stamp 说谎）。显式 evidence 参数仍原样直写。"""
        (tmp_path / "EVIDENCE-2026-08-24.md").write_text("old", encoding="utf-8")
        (tmp_path / "EVIDENCE-2026-08-26.md").write_text("new", encoding="utf-8")
        monkeypatch.setattr(mut, "STAMP", tmp_path / "evidence-stamp.json")
        monkeypatch.setattr(mut, "perimeter_blob", lambda: "fake-blob")
        blob = mut.write_stamp()
        stamp = json.loads((tmp_path / "evidence-stamp.json").read_text(encoding="utf-8"))
        assert blob == "fake-blob"
        assert stamp["evidence"] == "EVIDENCE-2026-08-26.md"
        # 显式 evidence 参数直写不改
        mut.write_stamp("EVIDENCE-2026-08-24.md")
        stamp2 = json.loads((tmp_path / "evidence-stamp.json").read_text(encoding="utf-8"))
        assert stamp2["evidence"] == "EVIDENCE-2026-08-24.md"
