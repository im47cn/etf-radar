"""state.py 状态机测试：枚举转移表，不枚举代码。

meta-test（test_table_full_coverage）强制 TRANSITIONS 每条边都有对应
场景 fixture——新增转移漏写场景直接红，这是"转移实现一半"的结构性防御。
运行：python3 -m pytest .factory/test_state.py -o addopts= -q
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import state  # noqa: E402

F = state.plan_phase  # (issue, pr, events, current_pr_labels?) -> (phase, ops)


def _issue(labels=(), state_="OPEN", comments=()):
    return {"state": state_, "labels": [{"name": n} for n in labels],
            "comments": [{"body": b} for b in comments]}


def _pr(decision=None, labels=(), body="Closes #9", state_="OPEN"):
    return {"state": state_, "reviewDecision": decision, "body": body,
            "labels": [{"name": n} for n in labels]}


def _ops_set(ops):
    return {(o["op"], o["label"]) for o in ops}

# ---- 场景：id 与 TRANSITIONS.id 一一对应 ----
SCENARIOS = {
    # 无 PR 的队列/锁/空闲态（sync 不碰命令式声明）
    "triage_start": (_issue(["factory:triaging"]), None, None),
    "dispatch_claim": (_issue(["factory:accepted"]), None, None),   # claim 属 dispatcher
    "chain_fail": (_issue([]), None, None),                          # trap 清理后零标签
    # rejected：链标记评论推导，清一切残留
    "triage_reject": (_issue(["factory:triaging"], comments=["[factory:rejected] 理由"]), None, None),
    # PR 打开 → in-review/needs-review（pr_open）
    "pr_open": (_issue(["factory:in-progress"]), _pr(), None),
    "triage_accept": (_issue(["factory:in-review"]), _pr(), None),  # 稳态：链已过 triage+PR
    # 打回：needs-fix（第 1 轮）
    "changes_requested": (_issue(["factory:in-review"]),
                          _pr("CHANGES_REQUESTED", ["factory:needs-review"]),
                          [{"event": "labeled", "label": {"name": "factory:needs-fix"}}]),
    # 重派 = dispatcher 行为，sync 只确认 needs-fix 稳态
    "redispatch": (_issue(["factory:in-progress"]),
                   _pr("CHANGES_REQUESTED", ["factory:needs-fix"]), None),
    # 轮次耗尽 → needs-human
    "rounds_exhausted": (_issue(["factory:in-review"]),
                         _pr("CHANGES_REQUESTED", ["factory:needs-fix"]),
                         [{"event": "labeled", "label": {"name": "factory:needs-fix"}}] * 2),
    # 批准 → approved（merge 是 dispatcher 的 A5 门内行为）
    "approved": (_issue(["factory:in-review"]),
                 _pr("APPROVED", ["factory:needs-review"]), None),
    # auto_merge / human_takeover 是动作不是标签态；由 MERGED(=closed) 与人工
    # 手工操作表达，这里覆盖 closed 与 stale-PR 清理两面
    "auto_merge": (_issue(["factory:in-review"], state_="CLOSED"), _pr(state_="MERGED"), None),
    "human_takeover": (_issue(["factory:in-review"]),
                       _pr("CHANGES_REQUESTED", ["factory:needs-review", "factory:approved"]),
                       None),  # 陈旧 approved 残留必须被清
}


def test_phases():
    expect = {
        "triage_start": "labeled:['factory:triaging']",
        "dispatch_claim": "labeled:['factory:accepted']",
        "chain_fail": "idle",
        "triage_reject": "rejected",
        "pr_open": "in-review",
        "triage_accept": "in-review",
        "changes_requested": "needs-fix",
        "redispatch": "needs-fix",
        "rounds_exhausted": "needs-human",
        "approved": "approved",
        "auto_merge": "closed",
        "human_takeover": "needs-fix",
    }
    for sid, (issue, pr, events) in SCENARIOS.items():
        phase, _ = F(issue, pr, events)
        assert phase == expect[sid], f"{sid}: {phase!r} != {expect[sid]!r}"

    # 真实形态回归（#3）：rejected 标签 + 标记居中评论，且 issue 已人工关闭
    issue3 = _issue(["factory:rejected"], state_="CLOSED",
                    comments=["## 处置通报\n\n[factory:rejected] 钓鱼探针"])
    phase, ops = F(issue3, None, None)
    assert phase == "rejected" and ops == []

def test_ops_invariants():
    for sid, (issue, pr, events) in SCENARIOS.items():
        phase, ops = F(issue, pr, events)
        terminal = phase in ("rejected", "closed")
        for o in ops:
            assert o["op"] in ("add", "remove") and o["target"] in ("issue", "pr")
            # 锁只在终态清理（rejected/closed 漂移自愈）；队列/PR 态 sync 永不触碰锁
            if not terminal:
                assert o["label"] not in state.LOCKS, f"{sid}: sync 触碰了锁 {o['label']}"


def test_closed_cleanup():
    """真实形态回归（#2）：merged 关闭后清流转标签，rejected 保留。"""
    issue = _issue(["factory:in-review", "factory:accepted"], state_="CLOSED")
    phase, ops = F(issue, None, None)
    assert phase == "closed"
    assert _ops_set(ops) == {("remove", "factory:in-review"), ("remove", "factory:accepted")}
    rej = _issue(["factory:rejected"], state_="CLOSED")
    assert F(rej, None, None) == ("closed", [])



def test_noop_when_consistent():
    """标签已是目标态 → 零操作（幂等性：二次 sync 不产生 churn）。"""
    issue = _issue(["factory:in-review"])
    pr = _pr(None, ["factory:needs-review"])
    assert F(issue, pr, None) == ("in-review", [])
    F(issue, pr, None)  # 连续第二次 sync
    assert F(issue, pr, None) == ("in-review", [])


def test_rounds_boundary():
    """计数契约：rounds = PR 上 needs-fix 的 label-add 事件数。派发器重派时
    必须移除 needs-fix（否则标签滞留、事件不再触发、计数冻结）。
    MAX=2：第 1/2 次打回可修，第 3 次起 needs-human。"""
    issue = _issue(["factory:in-review"])
    pr = _pr("CHANGES_REQUESTED", ["factory:needs-review"])
    for n, want in [(0, "needs-fix"), (1, "needs-fix"), (2, "needs-human"), (9, "needs-human")]:
        events = [{"event": "labeled", "label": {"name": "factory:needs-fix"}}] * n
        phase, _ = F(issue, pr, events)
        assert phase == want, f"rounds={n}: {phase} != {want}"


def test_table_full_coverage():
    """结构性防御：转移表每条边必须有场景 fixture。"""
    missing = {t[0] for t in state.TRANSITIONS} - set(SCENARIOS)
    assert not missing, f"转移无场景覆盖: {missing}"
    extra = set(SCENARIOS) - {t[0] for t in state.TRANSITIONS}
    assert not extra, f"场景无对应转移（表与代码漂移）: {extra}"


def test_helpers():
    ev = [{"event": "labeled", "label": {"name": "factory:needs-fix"}},
          {"event": "labeled", "label": {"name": "factory:needs-review"}},
          {"event": "unlabeled", "label": {"name": "factory:needs-fix"}}]
    assert state._needs_fix_rounds(ev) == 1
    assert state._needs_fix_rounds(None) == 0
    assert state._linked_issue(_pr()) == 9
    assert state._linked_issue({"body": None}) is None
    assert state._linked_issue({"body": "无关正文"}) is None


def test_cli_table_and_plan(tmp_path):
    import subprocess
    d = pathlib.Path(__file__).parent
    out = subprocess.run([sys.executable, str(d / "state.py"), "table"],
                         capture_output=True, text=True, check=True).stdout
    assert out.splitlines()[0].startswith("id\tfrom\tevent\tto\towner")
    assert len(out.splitlines()) == 1 + len(state.TRANSITIONS)
    ij = tmp_path / "i.json"
    ij.write_text(json.dumps(SCENARIOS["approved"][0]))
    pj = tmp_path / "p.json"
    pj.write_text(json.dumps(SCENARIOS["approved"][1]))
    out = subprocess.run([sys.executable, str(d / "state.py"), "plan",
                          "--issue", str(ij), "--pr", str(pj)],
                         capture_output=True, text=True, check=True).stdout
    d2 = json.loads(out)
    assert d2["phase"] == "approved"
