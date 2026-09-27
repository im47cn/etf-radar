"""regression_routing 负控制：日回归失败投递路由（L2 滞留接线）。

2026-09-15 issue #165 实证：旧实现只看标题复用 open 回归 issue，失败结果
投进 in-progress 留守（派发器永久跳过）的容器，5 天静默。本套件钉死
路由决策三态与 #165 事故形态——若路由回退为 append-only，用例即红。
"""
import io
import json
import sys
import time

import factory_lib


def _issue(labels):
    return {"number": 165, "title": "[factory-regression] x", "labels": labels}


# -- 正向：四态路由（lease_alive 维度）--------------------------------------

def test_in_progress_stalled_routes_wake():
    # #165 事故形态：零改动轮留守 accepted+in-progress，租约已死
    assert factory_lib.regression_routing(
        _issue(["factory:accepted", "factory:in-progress"]),
        lease_alive=False) == "wake"


def test_in_progress_live_chain_routes_live():
    # 审查 major（2026-09-16）：修复链在途时剥 in-progress 会使 §7.5
    # 留守对该轮失效——必须只追加不唤醒
    assert factory_lib.regression_routing(
        _issue(["factory:in-progress"]), lease_alive=True) == "live"


def test_in_progress_unknown_lease_routes_live():
    # PG 形态/判定失败：保守不自动唤醒
    assert factory_lib.regression_routing(
        _issue(["factory:in-progress"]), lease_alive=None) == "live"


def test_in_progress_default_unknown_routes_live():
    assert factory_lib.regression_routing(
        _issue(["factory:in-progress"])) == "live"


def test_rejected_routes_new():
    assert factory_lib.regression_routing(_issue(["factory:rejected"])) == "new"


def test_plain_and_human_states_route_append():
    for labels in ([], ["factory:accepted"], ["factory:in-review"],
                   ["factory:needs-human"]):
        assert factory_lib.regression_routing(_issue(labels)) == "append"


# -- 负控制：事故路径必须不是 append ----------------------------------------

def test_in_progress_stalled_must_not_append_or_live():
    # 负控制（#165 事故回归面）：滞留态若路由 append/live，失败结果进死信筒
    assert factory_lib.regression_routing(
        _issue(["factory:in-progress"]), lease_alive=False) == "wake"


def test_live_chain_must_not_wake():
    # 负控制（审查 major）：存活链被唤醒 = 留守语义被破坏 + 同诉求重派
    assert factory_lib.regression_routing(
        _issue(["factory:in-progress"]), lease_alive=True) != "wake"


def test_rejected_must_not_append():
    # 负控制：rejected 容器若路由 append，新失败进人工已拒死信筒
    assert factory_lib.regression_routing(_issue(["factory:rejected"])) != "append"


def test_anomalous_both_labels_prefers_wake():
    # 状态机互斥被数据打破时，可自动处置的路由优先（须以滞留态为前提）
    assert factory_lib.regression_routing(
        _issue(["factory:in-progress", "factory:rejected"]),
        lease_alive=False) == "wake"


def test_missing_labels_key_tolerated():
    assert factory_lib.regression_routing({"number": 1}) == "append"


# -- CLI 子命令：stdin JSON → stdout 决策 -----------------------------------

def test_cli_subcommand(monkeypatch, capfd):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_issue(
        ["factory:accepted", "factory:in-progress"]))))
    rc = factory_lib.main(["factory_lib.py", "regression-routing", "dead"])
    out = capfd.readouterr().out.strip()
    assert rc == 0 and out == "wake"


def test_cli_lease_fresh(tmp_path, capfd):
    lock = tmp_path / "issue:1.lock"
    lock.write_text("mid|7|123|0|900")  # 新建文件 mtime=now → 活
    assert factory_lib.main(["factory_lib.py", "lease-fresh", str(lock)]) == 0
    import os
    old = time.time() - 2000
    os.utime(lock, (old, old))          # mtime+900 < now → 过期残锁
    assert factory_lib.main(["factory_lib.py", "lease-fresh", str(lock)]) == 1
    assert factory_lib.main(
        ["factory_lib.py", "lease-fresh", str(tmp_path / "none.lock")]) == 1
    # 畸形内容（单字段非数字）回退 900：新鲜 mtime 仍判活，过期判死
    lock.write_text("garbage")
    assert factory_lib.main(["factory_lib.py", "lease-fresh", str(lock)]) == 0
    os.utime(lock, (old, old))
    assert factory_lib.main(["factory_lib.py", "lease-fresh", str(lock)]) == 1
