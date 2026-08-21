#!/usr/bin/env python3
"""factory 状态机核心：标签 = 仓库可见事实的纯函数（可推导态）。

第一性原理（防"转移实现一半"）：
- 可观测状态不由转移时刻的散落命令维护，而由 sync 从 GitHub 真实状态
  （PR 存在性 / reviewDecision / 标签事件计数 / 链标记评论）推导。
  忘写一个转移在这里不可能发生——没有转移代码，只有状态函数。
- 例外：triaging / in-progress 是锁（本地进程运行中的独占声明），
  锁必须命令式，且只有一个属主写（chain 设 triaging，dispatcher 设
  in-progress）。sync 永不触碰锁。
- TRANSITIONS 表是状态的唯一权威 spec；测试枚举表而非枚举代码，
  新增转移必须同时新增场景 fixture，否则 meta-test 失败。

输入（gh JSON，stdin 或 --issue/--pr/--events 文件）：
  issue: gh issue view N --json number,state,labels,comments
  pr:    gh pr view P --json number,state,reviewDecision,labels
  events: gh api repos/O/R/issues/P/events  （needs-fix 计数）
输出：{"phase":..., "ops":[{"target":"issue|pr","op":"add|remove","label":...}]}
CLI:
  state.py plan   [--issue F] [--pr F] [--events F]   # 纯计算，可测
  state.py table                                              # 转移表 TSV
"""
import json
import re
import sys

MAX_FIX_ROUNDS = 2  # 设计 §7：needs-fix ≤2 次后 needs-human

# 转移表：id 必须与 test_state.py 场景 id 一一对应（meta-test 强制全覆盖）
TRANSITIONS = [
    # id                        from         event              to          owner
    ("triage_start",            "",           "chain_start",     "triaging",    "chain"),
    ("triage_accept",           "triaging",   "verdict=accept",  "accepted",    "chain"),
    ("triage_reject",           "triaging",   "verdict=reject",  "rejected",    "chain"),
    ("dispatch_claim",          "accepted",   "dispatcher抢占",  "in-progress", "dispatcher"),
    ("chain_fail",              "in-progress", "链失败(trap)",    "",            "dispatcher"),
    ("pr_open",                 "in-progress", "PR创建",          "in-review",   "sync"),
    ("changes_requested",       "in-review",  "CHANGES_REQUESTED", "needs-fix", "sync"),
    ("redispatch",              "needs-fix",  "rounds<MAX重派",  "in-progress", "dispatcher"),
    ("rounds_exhausted",        "needs-fix",  "rounds>=MAX",     "needs-human", "sync"),
    ("approved",                "in-review",  "reviewDecision=APPROVED", "approved", "sync"),
    ("auto_merge",              "approved",   "A5门开",          "MERGED",      "dispatcher"),
    ("human_takeover",          "needs-human", "人工接管",        "(any)",       "human"),
]

LOCKS = {"factory:triaging", "factory:in-progress"}
QUEUE = {"factory:accepted"}
PR_SIDE = {"factory:needs-review", "factory:needs-fix", "factory:needs-human", "factory:approved"}


def _labels(obj):
    return {l["name"] for l in (obj or {}).get("labels", [])}


def _needs_fix_rounds(events):
    return sum(1 for e in events or []
               if e.get("event") == "labeled"
               and (e.get("label") or {}).get("name") == "factory:needs-fix")


def _linked_issue(pr):
    """链约定：PR body 含 'Closes #N'。"""
    m = re.search(r"[Cc]loses #(\d+)", (pr or {}).get("body") or "")
    return int(m.group(1)) if m else None


def plan_phase(issue, pr, events, current_pr_labels=None):
    """纯函数：给定 GitHub 事实 → (phase, ops)。issue 侧与 PR 侧标签一起算。"""
    ops = []

    def add(target, label):
        ops.append({"target": target, "op": "add", "label": label})

    def remove(target, label):
        ops.append({"target": target, "op": "remove", "label": label})

    issue_labels = _labels(issue)
    pr_labels = set(current_pr_labels if current_pr_labels is not None else _labels(pr))

    # 链标记评论 → rejected（#3 实测形态：标记在正文任意位置，子串匹配；
    # 误报风险=正文引用标记，可接受——标记只由链写）
    if any("[factory:rejected]" in (c.get("body") or "")
           for c in (issue or {}).get("comments", [])):
        for l in sorted(issue_labels - {"factory:rejected"}):
            remove("issue", l)
        if "factory:rejected" not in issue_labels:
            add("issue", "factory:rejected")
        return "rejected", ops

    if (issue or {}).get("state") == "CLOSED":
        # 终态清理：merged/人工关闭后，流转标签是噪音（label 搜索会命中
        # 已完结 issue）；rejected 作为链裁决记录保留
        for l in sorted(issue_labels - {"factory:rejected"}):
            remove("issue", l)
        return "closed", ops

    if not pr or pr.get("state") != "OPEN":
        # 无 PR：锁与队列态是命令式声明，sync 不碰（rejected 仅报告）
        have = issue_labels & (LOCKS | QUEUE | {"factory:rejected"})
        return f"labeled:{sorted(have)}" if have else "idle", []

    # PR 打开：issue 侧统一 in-review（状态接管）
    for l in sorted((issue_labels - LOCKS - {"factory:in-review"})
                    - {"factory:accepted", "factory:rejected"}):
        remove("issue", l)
    if "factory:in-review" not in issue_labels:
        add("issue", "factory:in-review")

    decision = pr.get("reviewDecision")
    rounds = _needs_fix_rounds(events)

    if decision == "APPROVED":
        phase = "approved"
        for l in sorted(pr_labels - PR_SIDE - {"factory:approved"}):
            remove("pr", l)
        if "factory:approved" not in pr_labels:
            add("pr", "factory:approved")
    elif decision == "CHANGES_REQUESTED":
        if rounds >= MAX_FIX_ROUNDS:
            phase = "needs-human"
            for l in sorted(pr_labels - PR_SIDE - {"factory:needs-human"}):
                remove("pr", l)
            if "factory:needs-human" not in pr_labels:
                add("pr", "factory:needs-human")
        else:
            phase = "needs-fix"
            for l in sorted(pr_labels - PR_SIDE - {"factory:needs-fix"}):
                remove("pr", l)
            if "factory:needs-fix" not in pr_labels:
                add("pr", "factory:needs-fix")
    else:  # 无裁决（REVIEW_REQUIRED / null）
        phase = "in-review"
        for l in sorted(pr_labels - PR_SIDE - {"factory:needs-review"}):
            remove("pr", l)
        if "factory:needs-review" not in pr_labels:
            add("pr", "factory:needs-review")
    return phase, ops


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "table":
        print("id\tfrom\tevent\tto\towner")
        for row in TRANSITIONS:
            print("\t".join(row))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "link":  # PR JSON → 关联 issue 号
        print(_linked_issue(json.load(open(sys.argv[2]))) or "")
        return

    args = sys.argv[1:]

    def load(flag):
        if flag in args:
            return json.load(open(args[args.index(flag) + 1]))
        return None

    issue = load("--issue")
    if issue is None and not sys.stdin.isatty():
        issue = json.load(sys.stdin)
    pr = load("--pr")
    events = load("--events")
    phase, ops = plan_phase(issue, pr, events)
    print(json.dumps({"phase": phase, "ops": ops}, ensure_ascii=False))


if __name__ == "__main__":
    main()
