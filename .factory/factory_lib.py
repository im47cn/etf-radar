#!/usr/bin/env python3
"""factory_lib —— 工厂链公共逻辑（从 bash 内联 heredoc 提取，使其可单测）。

提取动机（S2 真实链暴露的三类缺陷，全部在本库固化语义并有回归测试）:
1. 解析崩溃: fence 正则捕获组 0 含 ```json 字面量 → JSONDecodeError 链死
   （2026-08-21 issue #2 首次 holdout 后链即死于此）。group(1) 语义在此固化。
2. 证据饥饿: -q 点号输出让 holdout 无法引用测试名 → 永远 FAIL。
   evidence_suites 保证触及的 skills 套件必产出 verbose 证据段。
3. 熔断判定曾藏于 dispatch.sh heredoc，无法独立验证边界（跨天/重置/上限）。

CLI:
  factory_lib.py parse   <logfile> <outjson> <allowed-csv>   # 解析 agent 输出 JSON
  factory_lib.py breaker <floor.json> <ledger.jsonl>         # 熔断检查（超限 exit 3）
  factory_lib.py suites  <file...>                           # 证据段套件清单
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path


class CircuitOpen(RuntimeError):
    """熔断打开：超日上限或连续失败上限。"""


def parse_agent_json(text: str, allowed: set[str]) -> dict:
    """从 agent stdout 提取（唯一）JSON 裁决对象。

    fence 优先（```json {...} ```），裸 JSON 贪心兜底；两者均取捕获组 1——
    组 0 含围栏字面量，loads 必炸（见模块 docstring 缺陷 1）。
    verdict 不在 allowed → ValueError（fail-closed，不让坏裁决流入链）。
    """
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        raise ValueError("输出中未找到 JSON 对象")
    d = json.loads(m.group(1))
    verdict = d.get("verdict")
    if verdict not in allowed:
        raise ValueError(f"verdict={verdict!r} 不在 {sorted(allowed)}")
    return d


def evidence_suites(changed_files: list[str]) -> list[str]:
    """变更文件 → 需 verbose 证据段的测试套件（布局双适配，2026-08-22 对账吸收）。

    monorepo（backend|frontend）与 skills/<name>/scripts 两种布局都识别；
    套件名与 scripts/run_tests.sh --evidence <suite> 的取值一一对应。
    不存在的套件由调用方（fix-issue.sh）的 -d 探测过滤，引擎不做仓假设。
    """
    suites = set()
    for f in changed_files:
        m = re.match(r"(backend|frontend)/", f)
        if m:
            suites.add(m.group(1))
            continue
        m = re.match(r"(skills/[^/]+)/", f)
        if m:
            suites.add(f"{m.group(1)}/scripts")
    return sorted(suites)


def breaker_check(floor: dict, entries: list[dict], today: str) -> None:
    """熔断判定：当日 runs 或连续失败 streak 超上限 → CircuitOpen。

    streak 跨全部历史条目（不只当日）：连续失败是状态不是流量。
    """
    runs = sum(1 for e in entries if str(e.get("ts", ""))[:10] == today)
    streak = 0
    for e in entries:
        streak = streak + 1 if e.get("exit") != 0 else 0
    if runs >= floor["max_runs_per_day"]:
        raise CircuitOpen(f"熔断：今日已跑 {runs} 次（上限 {floor['max_runs_per_day']}）")
    if streak >= floor["max_consecutive_failures"]:
        raise CircuitOpen(
            f"熔断：连续失败 {streak} 次（上限 {floor['max_consecutive_failures']}），需人工介入"
        )


def _load_ledger(path: str) -> list[dict]:
    entries = []
    ledger = Path(path)
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


# 节点预算（S3 实测校准：#2/#5 链——裁决器秒级、prime/plan/review 分钟级、
# implement 十分钟级）。env 覆盖：FACTORY_TIMEOUT_<NODE>（单节点）>
# FACTORY_TIMEOUT（全局兜底）> 下表默认。
NODE_TIMEOUTS = {
    "triage": "5m",      # 无工具裁决器，实测 ~10s
    "holdout": "5m",     # 无工具验证器，实测 ~15s
    "prime": "15m",
    "plan": "15m",
    "review": "15m",
    "pr-review": "15m",
    "implement": "30m",  # P95 未知前保守；ledger.secs 积累后按分布再调
}


def node_timeout(name: str, env: dict | None = None) -> str:
    env = env if env is not None else {}
    per_node = env.get(f"FACTORY_TIMEOUT_{name.upper().replace('-', '_')}")
    return per_node or env.get("FACTORY_TIMEOUT") or NODE_TIMEOUTS.get(name, "15m")

def classify_task(files: list[str]) -> str:
    """变更文件 → 任务类型（成本归因用；doc/code 分开统计预算分布）。

    rejected（triage 拒绝）由调用方直接写 "rejected"，不走本函数。
    规则：全 .md → doc；纯测试文件（无 md 无 src）→ test；
    md 与任何代码（含测试）并存 → mixed；其余纯代码 → code。
    """
    if not files:
        return "empty"

    def _is_test(f: str) -> bool:
        # 前端约定也算 test（PR #69 审查）：.test.* / .spec.* / __tests__
        return ("/tests/" in f or f.startswith("tests/")
                or "/__tests__/" in f or f.startswith("__tests__/")
                or "/test_" in f or f.startswith("test_")
                or ".test." in f or ".spec." in f)

    md = [f for f in files if f.endswith((".md", ".mdx"))]
    code = [f for f in files if not f.endswith((".md", ".mdx"))]
    tests = [f for f in code if _is_test(f)]
    src = [f for f in code if not _is_test(f)]
    if not code:
        return "doc"
    if not src and not md:
        return "test"
    if md:  # md 与任何代码（含测试）并存
        return "mixed"
    return "code"



# 重投指引模板：键 = 未通过的 MISSION 判据（a 使命一致 / b 可判定 / c 不触周界）
REJECT_GUIDANCE: dict[str, str] = {
    "a": "判据a（使命一致）：写明落点组件——backend 流水线（providers/scoring/output/etl）、frontend 页面与组件、既有测试、或文档；",
    "b": "判据b（可判定）：把完成标准写成可机械验证的形式——验收 = 具体测试/脚本的断言（公式、逐条清单、file:line 级差异），避免「持续 / 优化 / 失修」类开放措辞；",
    "c": "判据c（不触周界）：触及 PERIMETER 的部分拆成独立 issue 走人类 PR（治理 / 质检线 / 数据面 / 依赖发布面清单见 MISSION.md）；",
}


def _neutralize_marker(text: str) -> str:
    """破坏文本中的裸标记子串（数据侧防注入）。

    triage reasons 是 LLM 产物，可能从 issue 评论回显 `[factory:rejected]`
    （用户以标记表达异议）。state.py 对 issue 评论做子串扫描，回执原样
    引用即被识别为人工覆盖 → 永久钉死 rejected。去括号保留语义、破坏
    子串；循环替换防 `[[...]]` 嵌套构造替换一次后重组出标记。
    """
    while "[factory:rejected]" in text:
        text = text.replace("[factory:rejected]", "factory:rejected")
    return text


def reject_receipt(triage: dict) -> str:
    """triage 裁决（reject）→ 拒绝回执 markdown（五段式：结论/依据/指引/关联/边界）。

    确定性渲染，零 LLM（链脚本纪律，铁律 4 同源）。安全不变量：**输出永不
    包含裸标记 `[factory:rejected]`**——模板侧字面量不写标记，数据侧
    （reasons，LLM 产物）经 _neutralize_marker 中和。state.py 标记评论通道
    优先级最高且无撤销语义，回执携带标记会把重投（MISSION：补充上下文后
    重开）永久钉死在 rejected；标记通道保留给人类手动覆盖（人写人删）。
    rejected 的机器状态由标签承载，人类审计由本回执承载。
    """
    raw = triage.get("reasons")
    reasons = raw if isinstance(raw, list) else []  # 标量/缺失 → 空，不抛 TypeError
    reasons = [_neutralize_marker(r) if isinstance(r, str) else r for r in reasons]
    lines = [
        "## 工厂 triage 裁决：reject",
        "",
        "**结论**：未通过 [MISSION.md](../blob/main/MISSION.md)「Triage 判据」，链已终止，issue 落标 factory:rejected。",
        "",
        "**依据**（物理隔离 triage 节点产出，逐条判据）：",
    ]
    lines += [f"- {r}" for r in reasons] or ["- （裁决器未给出判据明细）"]

    failed: set[str] = set()
    for r in reasons:
        if not isinstance(r, str):  # LLM 偶发非字符串元素：跳过匹配，
            continue                # 不让回执阶段崩掉整条链的评论
        m = re.match(r"^判据([abc])[:：]", r)
        if m and ("不通过" in r or "存疑" in r):
            failed.add(m.group(1))
    lines += ["", "**重投指引**：不同意裁决可补充上下文后重开，下一轮 triage 全新评估。针对未通过判据："]
    lines += [f"- {REJECT_GUIDANCE[k]}" for k in sorted(failed)] or [
        "- 对照 MISSION.md「Triage 判据」逐条补足 issue 上下文。"
    ]

    lines += [
        "",
        "── 关联 ──",
        "  未识别出因果相关模块——triage 节点 --no-tools 无仓库事实核对能力，",
        "  且拒绝裁决不产生代码变更，无下游影响面；重投协议见 .factory/README.md。",
        "",
        "── 证据边界 ──",
        "  已验证: 判据核对——triage 节点（--no-tools 物理隔离，输入仅 MISSION 全文 + issue 标题正文）",
        "  未覆盖: 仓库事实核对（裁决器无工具权限，不做代码 / 数据检索；重投前请补足具体事实）",
        "  置信度: 二值裁决基于 issue 文本与 MISSION 判据核对，无运行时验证",
        "",
    ]
    assert "[factory:rejected]" not in "\n".join(lines)  # 双保险：模板+数据中和后仍断言
    return "\n".join(lines)

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "classify":
        print(classify_task(argv[2:]))
        return 0
    if cmd == "timeout":
        print(node_timeout(argv[2]))
        return 0
    if cmd == "receipt":
        # receipt <triage.json> —— 拒绝回执 markdown（确定性模板，零 LLM）
        print(reject_receipt(json.loads(Path(argv[2]).read_text(encoding="utf-8"))))
        return 0
    if cmd == "parse":
        # parse <logfile> <outjson> <allowed-csv>
        text = Path(argv[2]).read_text(encoding="utf-8")
        d = parse_agent_json(text, set(argv[4].split(",")))
        Path(argv[3]).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    if cmd == "breaker":
        floor = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        entries = _load_ledger(argv[3])
        try:
            breaker_check(floor, entries, datetime.date.today().isoformat())
        except CircuitOpen as exc:
            print(exc, file=sys.stderr)
            return 3
        return 0
    if cmd == "report":
        # report <node-metrics.jsonl...>：P50/P95/预算建议（数据源=每链 node-metrics.jsonl）
        rows = []
        for f in argv[2:]:
            rows += _load_ledger(f)
        by_node: dict[str, list[int]] = {}
        for e in rows:
            if e.get("status") == "ok":
                by_node.setdefault(e["node"], []).append(int(e["secs"]))
        if not by_node:
            print("尚无成功样本"); return 0
        def pct(xs, q):
            xs = sorted(xs); i = max(0, min(len(xs) - 1, round(q * (len(xs) - 1))))
            return xs[i]
        for node in sorted(by_node):
            xs = by_node[node]
            cur = NODE_TIMEOUTS.get(node, "15m")
            p95 = pct(xs, 0.95)
            suggest = max(5, int(p95 / 60) + 2)  # P95 分钟 + 2 分钟余量，下限 5m
            print(f"{node:10s} n={len(xs):2d}  p50={pct(xs,0.5):5d}s  p95={p95:5d}s  预算={cur}  建议≤{suggest}m")
        return 0
    if cmd == "suites":
        for s in evidence_suites(argv[2:]):
            print(s)
        return 0
    print(f"未知子命令: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
