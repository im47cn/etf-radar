#!/usr/bin/env python3
"""factory_lib —— 工厂链公共逻辑（从 bash 内联 heredoc 提取，使其可单测）。

提取动机（S2 真实链暴露的三类缺陷，全部在本库固化语义并有回归测试）:
1. 解析崩溃: fence 正则捕获组 0 含 ```json 字面量 → JSONDecodeError 链死
   （2026-08-21 issue #2 首次 holdout 后链即死于此）。group(1) 语义在此固化。
2. 证据饥饿: -q 点号输出让 holdout 无法引用测试名 → 永远 FAIL。
   evidence_suites 保证触及的 skills 套件必产出 verbose 证据段。
3. 熔断判定曾藏于 dispatch.sh heredoc，无法独立验证边界（跨天/重置/上限）。
4. dispatch 进程编排（后台链/wait/并发槽/硬锁）曾为 bash 进程原语，缺陷类
   聚集（docs/adr/ADR-002-a3-maintenance-ledger.md）；2026-08-24 下沉本文件（ADR-005）。

CLI:
  factory_lib.py parse   <logfile> <outjson> <allowed-csv>   # 解析 agent 输出 JSON
  factory_lib.py breaker <floor.json> <ledger.jsonl>         # 熔断检查（超限 exit 3）
  factory_lib.py suites  <file...>                           # 证据段套件清单
  factory_lib.py sanitize <file...>                          # 标记中和（原地写回，幂等；评论出口必经）
  factory_lib.py rejected-reconcile < issues.json            # rejected 存量对账报告（TSV）
  factory_lib.py dispatch [--dry-run] [--watch] [--interval N]  # S2 派发器（dispatch.sh shim 的实现体）
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# 字节码密闭（issue #107）：本文件常以 `python3 factory_lib.py` 子进程方式被
# sync/dispatch 等脚本调用，import hosting 会在调用方仓的 .factory/ 留下
# 未跟踪 __pycache__——污染下游仓「落库后工作树干净」断言与巡检。hosting
# 是本仓唯一仓内 import，只需在其导入期间禁写字节码（pyc 写入发生在被导入
# 模块执行前），随后恢复原值——避免本模块被 pytest 等长生命周期进程 import
# 时永久改变宿主进程的全局缓存行为（__main__ 自身不缓存；本模块在 pytest
# 进程中的自身缓存由根 .gitignore 兜底）。
_previous_dont_write_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    import hosting  # 托管平台抽象层（ADR-008）：中立 schema，gh/云效差异在其内
finally:
    sys.dont_write_bytecode = _previous_dont_write_bytecode


class CircuitOpen(RuntimeError):
    """熔断打开：超日上限或连续失败上限。"""


def parse_agent_json(text: str, allowed: set[str]) -> dict:
    r"""从 agent stdout 扫描返回首个 verdict 合法的完整 JSON 裁决对象。

    fence 优先（```json 是 LLM 显式结构化输出信号，穷尽全部 fence 才轮到
    裸对象——首个 fence 裁决非法不压制后位合法 fence）；其后按文档序逐 `{`
    偏移 raw_decode——#207 实证贪心 `\{.*\}` 把「重复 JSON / 带花括号
    尾文」从首 `{` 拼到末 `}`（Extra data: char 429）一次即崩；多对象
    并存取首个合法者（重复块即恢复形态）。顶层 verdict 契约（PR #211
    Sourcery 评论1）：对象一旦完整解析，其内部偏移全部丧失资格——
    外层 verdict 非法时嵌套 evidence/元数据携带的合法 verdict 不代表
    裁决（防坏裁决借嵌套混入链）；坏 verdict 跳过其整个对象继续扫后续
    顶层；解码失败的对象按字符串感知平衡范围整体跳过（未闭合则跳到
    输入末尾——CodeRabbit 评论2：坏外层不得放行嵌套 verdict）；
    无任何合法对象 → ValueError（fail-closed）。
    """
    dec = json.JSONDecoder()

    def _decode(i: int) -> tuple[dict, int] | None:
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            return None
        return (obj, end) if isinstance(obj, dict) else None

    def _balanced_end(start: int) -> int | None:
        """depth-0 `{` 起字符串感知扫描平衡闭区间终点（闭 `}` 后一位）；
        未闭合返回 None（其后内容视为对象内部，一并放弃）。"""
        depth = 0
        in_str = esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
        return None

    for m in re.finditer(r"```json\s*(\{)", text):
        hit = _decode(m.start(1))
        if hit is not None and hit[0].get("verdict") in allowed:
            return hit[0]
    # 文档序扫描：对象一旦完整解析，[i, end) 内的嵌套偏移全部跳过
    # ——顶层 verdict 契约（嵌套 verdict 不代表裁决）
    skip_until = 0
    for i in sorted({i for i, ch in enumerate(text) if ch == "{"}):
        if i < skip_until:
            continue
        hit = _decode(i)
        if hit is None:
            # 解码失败的对象整体跳过其平衡范围，不许嵌套 `{` 接管裁决
            end = _balanced_end(i)
            skip_until = len(text) if end is None else end
            continue
        obj, skip_until = hit
        if obj.get("verdict") in allowed:
            return obj
    raise ValueError(
        f"输出中未找到 JSON 裁决对象（合法 verdict ∈ {sorted(allowed)}）")


def evidence_suites(changed_files: list[str]) -> list[str]:
    """变更文件 → 需 verbose 证据段的测试套件（布局双适配，M4）。

    monorepo（backend|frontend）与 skills/<name>/scripts 两种布局都识别
    （对齐 下游生产版）；套件名与测试门 --evidence <suite> 的取值
    一一对应。不存在的套件由调用方（fix-issue.sh）的 -d 探测过滤，
    引擎不做仓假设——双布局识别让本函数零本地化（full 分发）。
    """
    suites = set()
    for f in changed_files:
        if m := re.match(r"(backend|frontend)/", f):
            suites.add(m[1])
            continue
        if m := re.match(r"(skills/[^/]+)/", f):
            suites.add(f"{m[1]}/scripts")
    return sorted(suites)


def breaker_check(floor: dict, entries: list[dict], today: str) -> None:
    """熔断判定：当日 runs 或连续失败 streak 超上限 → CircuitOpen。

    streak 跨全部历史条目（不只当日）：连续失败是状态不是流量。
    """
    runs = sum(str(e.get("ts", ""))[:10] == today for e in entries)
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
            if line := line.strip():
                entries.append(json.loads(line))
    return entries


# 节点预算（S3 实测校准：#2/#5 链——裁决器秒级、prime/plan/review 分钟级、
# implement 十分钟级）。env 覆盖：FACTORY_TIMEOUT_<NODE>（单节点）>
# FACTORY_TIMEOUT（全局兜底）> 下表默认。
# 重校准（2026-09-04，#113/#123/#124/#131 四链 28 节点次，ok-run P95）：
# 口径 max(P95×1.2, 下列默认) 向上取整分钟——implement 1534s→31m、
# review 845s→17m 上调；prime 687.6s / plan 882s / 裁决器均低于默认，不动。
# 注意 report 子命令的建议口径（仅 ok-run P95+2m）不含撞顶截尾观测，
# 手工复核时应将「no-artifact 且 secs≥预算」的行按预算值计入下界。
NODE_TIMEOUTS = {
    "triage": "5m",      # 无工具裁决器，P95 144s
    "holdout": "5m",     # 无工具验证器，P95 86s
    "prime": "20m",      # 旧样 P95×1.2=687.6s 已过期：现测 865/884s 贴顶、900s 撞顶（#165 r6）→ 20m
    "plan": "20m",       # 旧样 P95×1.2=882s 已过期：#165 r4 实测 901s 压线过 → 20m
    "review": "30m",     # 17m 撞顶（原 15m→17m 仍不够）：#165 r2/r3 1026/1021s 败、r4 1020s 压线 → 30m
    "pr-review": "15m",  # 无 ok-run 样本，维持默认
    "implement": "31m",  # P95 1534s×1.2=1840.8s → 31m（原 30m 撞顶 #113 r1）
}


def node_metric_line(node: str, t0: int, now: int, status: str) -> str:
    """节点级计时 jsonl 行（report 子命令的数据源）。

    ADR-005 缺陷驱动下沉（2026-08-27）：fix-issue.sh / validate-pr.sh 各自
    内嵌的逐字节等价 heredoc 收口至此（shell 侧仅留调用 wrapper，与
    node_timeout 同款）；渲染契约与消费端（report）同模块，drift 即测试红。
    """
    return json.dumps(
        {"node": node, "secs": now - t0, "status": status}, ensure_ascii=False
    )


def node_timeout(name: str, env: dict | None = None) -> str:
    # 未显式传 env 时读进程环境：CLI（factory_lib.py timeout <node>）由此获得
    # FACTORY_TIMEOUT_*/FACTORY_TIMEOUT 覆盖能力（launchd/cron 免 PR 调预算）。
    env = env if env is not None else os.environ
    per_node = env.get(f"FACTORY_TIMEOUT_{name.upper().replace('-', '_')}")
    return per_node or env.get("FACTORY_TIMEOUT") or NODE_TIMEOUTS.get(name, "15m")


def jfield(path: str, key: str, default: str | None = None) -> int:
    """json 字段取值（shell json_field wrapper 的实现体，2026-08-28 收口）。

    原 fix-issue.sh 形态 `python3 -c "…print($2)"` 把 shell 变量内插进
    Python 源码——静态不可验证，check_inline_python R4 已禁形。契约 =
    原三种调用形态：jfield <file> <key> [default]；键缺失/值为 null →
    default（未给则 rc=1，stderr 指明缺键——shell 侧空串+非零，fail-closed）；
    非 str 值以 JSON 编码输出，保持 shell 比较确定性。
    """
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    v = d.get(key) if isinstance(d, dict) else None
    if v is None:
        if default is None:
            print(f"jfield: {path} 缺键 {key}（或值为 null）", file=sys.stderr)
            return 1
        v = default
    print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return 0

def classify_task(files: list[str]) -> str:
    """变更文件 → 任务类型（成本归因用；doc/code 分开统计预算分布）。

    rejected（triage 拒绝）由调用方直接写 "rejected"，不走本函数。
    规则：全 .md → doc；纯测试文件（无 md 无 src）→ test；
    md 与任何代码（含测试）并存 → mixed；其余纯代码 → code。
    """
    if not files:
        return "empty"

    def _is_test(f: str) -> bool:
        # 前端约定也算 test（源仓#69 审查）：.test.* / .spec.* / __tests__
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
    return "mixed" if md else "code"


# 工厂本地化配置（M4 + 拆分前置 ADR-009）：guard.py / 链脚本 / prompts 的
# 仓特定内容（周界、判据措辞、门命令、仓库参数、上游指针）统一由
# factory-local.json 提供——本文件零本地化、跨仓 full 分发。
# fail-closed：配置缺失/损坏/缺键 → RuntimeError（调用方非零退出，禁止降级）。
def _load_local_cfg() -> dict:
    cfg_path = Path(__file__).resolve().parent / "factory-local.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("顶层不是对象")
    except Exception as exc:
        raise RuntimeError(f"factory-local.json 不可用（fail-closed）: {exc}") from exc
    return cfg


_LOCAL_CFG: dict = _load_local_cfg()


def _local_str(key: str) -> str:
    try:
        v = _LOCAL_CFG[key]
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"键 {key} 须为非空字符串")
        return v
    except Exception as exc:
        raise RuntimeError(f"factory-local.json 键 {key} 不可用（fail-closed）: {exc}") from exc


def _local_str_list(key: str) -> list[str]:
    try:
        v = _LOCAL_CFG[key]
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x.strip() for x in v):
            raise ValueError(f"键 {key} 须为非空字符串数组")
        return list(v)
    except Exception as exc:
        raise RuntimeError(f"factory-local.json 键 {key} 不可用（fail-closed）: {exc}") from exc


# 重投指引模板：键 = 未通过的 MISSION 判据（a 使命一致 / b 可判定 / c 不触周界）。
# M4 本地化外置（设计 §11.3）：措辞锚定各仓 MISSION。fail-closed：配置缺失/
# 缺键 → RuntimeError（triage 回执生成失败，链侧 issue_reject 降级为回执告警）。
def _load_reject_guidance() -> dict[str, str]:
    try:
        rg = _LOCAL_CFG["reject_guidance"]
        return {k: str(rg[k]) for k in ("a", "b", "c")}
    except Exception as exc:
        raise RuntimeError(f"factory-local.json reject_guidance 不可用: {exc}") from exc


REJECT_GUIDANCE: dict[str, str] = _load_reject_guidance()


def final_gate_cmd() -> str:
    """确定性测试门命令（整条 shell 词序列，取值见 factory-local.json）。

    ADR-009 门命令数据化：fix-issue / validate-pr / mutations 共用此配置，
    消灭三处硬编码漂移面。拆词由调用方执行——bash 侧 read -r -a 与
    mutations 侧 shlex.split 的语义分叉点有三：引号（shlex 剥除、read
    字面）、反斜杠（shlex 转义、read -r 字面——`a\\ b` 两侧词数即不同：
    2 词 vs 1 词）与换行（read -r -a 只取 here-string 首行，shlex 多行
    拆词）。故配置值**禁含引号、反斜杠与换行**（引号 review R2-M8；反斜杠
    ADR-010 漂移锁收口；换行 ts#19 审查收口），含即 fail-closed；纯空白
    分隔下两拆词器逐词一致，两门 argv 永远相等。
    """
    v = _local_str("final_gate_cmd")
    if "'" in v or '"' in v:
        raise RuntimeError("final_gate_cmd 禁含引号（read -r -a 与 shlex 拆词一致性）")
    if "\\" in v:
        raise RuntimeError("final_gate_cmd 禁含反斜杠（shlex 转义与 read -r 字面语义分叉，ADR-010）")
    if "\n" in v or "\r" in v:
        raise RuntimeError("final_gate_cmd 禁含换行（read -r -a 只取首行，shlex 多行拆词，两侧 argv 分歧）")
    return v


def docstring_gate_cmd() -> str | None:
    """docstring 门命令（可选键，缺省不启用；取值见 factory-local.json）。

    与 final_gate_cmd 同构但为**可选**门：键缺失/不存在 → 返回 None（链脚本
    跳过，仓库无 docstring 门）；键存在 → 语义与 final_gate_cmd 完全一致
    （非空字符串 + 禁引号/反斜杠/换行，fail-closed：配置损坏即 RuntimeError，
    禁止静默降级为无门）。对外 API 100% 可文档化 + 内部 API ≥80% 的阈值由
    各仓检查器自定（语言 AST 异构，不在此数据化），本键只承载命令。
    """
    if "docstring_gate_cmd" not in _LOCAL_CFG:
        return None
    v = _local_str("docstring_gate_cmd")
    if "'" in v or '"' in v:
        raise RuntimeError("docstring_gate_cmd 禁含引号（read -r -a 与 shlex 拆词一致性）")
    if "\\" in v:
        raise RuntimeError("docstring_gate_cmd 禁含反斜杠（shlex 转义与 read -r 字面语义分叉，ADR-010）")
    if "\n" in v or "\r" in v:
        raise RuntimeError("docstring_gate_cmd 禁含换行（read -r -a 只取首行，shlex 多行拆词，两侧 argv 分歧）")
    return v

_PARALLEL_STACKS = frozenset({
    "pytest", "maven", "gradle", "jest", "vitest", "go", "cargo", "phpunit", "dotnet",
})
_PARALLEL_SEGMENT_KEYS = frozenset({"tag", "name", "argv", "shell", "cwd", "intra", "stack"})


def parallel_gate_cfg() -> dict | None:
    """并行测试门配置（可选键 parallel_gate，缺省不启用；ADR-016）。

    与 docstring_gate_cmd 同为**可选键**范式：键缺失 → None（本仓未采用
    并行门，零行为变化）；键存在 → 严格校验，损坏即 RuntimeError
    （fail-closed：可选 ≠ 静默降级为旧串行门——门是裁决路径，配置坏了
    必须炸，不能悄悄不并行或漏跑段）。schema 拒绝未知键：本键的失效
    形态是「静默慢」（拼错 intra/segments 导致能力没开、段没跑），与
    final_gate_cmd 的禁引号约束同理，宁可误伤不可漏拦。

    结构：{"workers": int≥0（0=不限并发，缺省 0）, "segments": [
      {"tag": 唯一标识（禁换行——宿主脚本按行回收失败段清单）,
       "name": 显示头（缺省=tag）, "argv": [词...] XOR "shell": "命令串",
       "cwd": 段工作目录（相对仓根，缺省=仓根）,
       "intra": "off"|"auto"（段内并行档，缺省 off——顺序敏感测试所在
       段保持串行，auto 是逐段显式 opt-in）,
       "stack": 显式测试栈（缺省按段 cwd 构建文件探测）}]}。
    argv 词 "$PY" 在执行期替换为解释器（env PYTHON 或 python3，逐字
    保留宿主仓门禁脚本的 PY 语义）；shell 段以 bash -o pipefail 执行，
    $1 = 解释器占位。
    """
    if "parallel_gate" not in _LOCAL_CFG:
        return None
    raw = _LOCAL_CFG["parallel_gate"]
    try:
        if not isinstance(raw, dict):
            raise ValueError("parallel_gate 须为对象")
        if unknown := set(raw) - {"segments", "workers"}:
            raise ValueError(f"未知顶层键: {sorted(unknown)}")
        segs_raw = raw.get("segments")
        if not isinstance(segs_raw, list) or not segs_raw:
            raise ValueError("segments 须为非空数组")
        seen: set[str] = set()
        segs: list[dict] = []
        for s in segs_raw:
            if not isinstance(s, dict):
                raise ValueError("段须为对象")
            tag = s.get("tag")
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("段缺 tag（非空字符串，失败聚合标识）")
            if "\n" in tag or "\r" in tag:
                raise ValueError(f"段 tag 禁换行（失败清单按行回收）: {tag}")
            if tag in seen:
                raise ValueError(f"段 tag 重复: {tag}")
            seen.add(tag)
            if bad_keys := set(s) - _PARALLEL_SEGMENT_KEYS:
                raise ValueError(f"段 {tag} 未知键: {sorted(bad_keys)}")
            # 二选一按「键存在」判（PR #220 评论）：{"argv": [], "shell":
            # "x"} 若按值判会双双通过 XOR，空 argv 落到 spawn 期才炸
            has_argv = "argv" in s
            has_shell = "shell" in s
            if has_argv == has_shell:
                raise ValueError(f"段 {tag}: argv（词数组）与 shell（命令串）二选一")
            if has_argv and (
                not isinstance(s["argv"], list)
                or not s["argv"]
                or not all(isinstance(w, str) and w for w in s["argv"])
            ):
                raise ValueError(f"段 {tag}: argv 词须为非空字符串")
            if has_shell and (
                not isinstance(s["shell"], str) or not s["shell"].strip()
            ):
                raise ValueError(f"段 {tag}: shell 须为非空字符串")
            intra = s.get("intra", "off")
            if intra not in ("off", "auto"):
                raise ValueError(f"段 {tag}: intra 取值 off|auto（得到 {intra!r}）")
            stack = s.get("stack")
            if stack is not None and stack not in _PARALLEL_STACKS:
                raise ValueError(f"段 {tag}: 未知 stack {stack!r}（合法: {sorted(_PARALLEL_STACKS)}）")
            norm = {"tag": tag, "name": s.get("name") or tag, "intra": intra}
            if "argv" in s:
                norm["argv"] = s["argv"]
            if "shell" in s:
                norm["shell"] = s["shell"]
            if "cwd" in s:
                if not isinstance(s["cwd"], str) or not s["cwd"].strip():
                    raise ValueError(f"段 {tag}: cwd 须为非空字符串")
                norm["cwd"] = s["cwd"]
            if stack is not None:
                norm["stack"] = stack
            segs.append(norm)
        workers = raw.get("workers", 0)
        if not isinstance(workers, int) or isinstance(workers, bool) or workers < 0:
            raise ValueError("workers 须为 ≥0 整数（0=不限并发）")
        return {"workers": workers, "segments": segs}
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"factory-local.json parallel_gate 不可用（fail-closed）: {exc}") from exc


def repo_vars_text() -> str:
    """拼进工作节点 prompt 的「仓库参数」段（prompts 零宿主专名的注入面）。

    run_node / pr-review / feedback-adapt 拼装 prompt 时追加本段；triage 与
    holdout 是物理隔离节点（无工具），不注入——其输入（MISSION/tests-output）
    已由链脚本内联。
    """
    lines = [
        "——仓库参数（本仓工厂本地化配置，prompt 正文不重复这些值）——",
        f"- 仓库身份: {_local_str('repo_identity')}",
        f"- 阅读范围（研究/评审自由阅读）: {'、'.join(_local_str_list('reading_scopes'))}",
        f"- 审查依据目录: {_local_str('review_basis')}",
        f"- final_gate 命令: {final_gate_cmd()}",
    ]
    if (dg := docstring_gate_cmd()) is not None:
        lines.append(f"- docstring 门命令: {dg}")
    if "pr_review_skills" in _LOCAL_CFG:
        # 键存在即严格校验（与 local-list 同规）：值损坏 fail-closed；
        # 键缺失 = 本仓无守卫技能面（如纯后端仓），合法省略该行。
        skills = _local_str_list("pr_review_skills")
        lines.append(f"- 守卫技能（PR 评审选配面）: {'、'.join(skills)}")
    return "\n".join(lines)


def dist_manifest_lines(up: str, sha: str) -> list[str]:
    """上游 DISTRIBUTION.json @sha → 分发清单行（kind\\trel_path）。

    清单是上游主权：从上游对象库读（下游本地副本可能滞后甚至缺失，锚点
    即版本）。目录项递归展开为文件项——full 语义对目录内每个文件成立
    （review R2-M5：跳过目录项 = tests/ 漂移永不告警）。上游无清单 =
    版本旧，返回空（调用方全部按 local 报告）。local 是 {路径: 理由}。
    """
    out = subprocess.run(
        ["git", "-C", up, "show", f"{sha}:.factory/DISTRIBUTION.json"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        print("警告: 上游无 DISTRIBUTION.json（版本旧），全部按 local 报告",
              file=sys.stderr)
        return []
    manifest = json.loads(out.stdout)
    lines: list[str] = []

    def emit(kind: str, entry: str) -> None:
        if entry.endswith("/"):
            # 目录项（如 tests/）递归展开为文件项
            r = subprocess.run(
                [
                    "git",
                    "-C",
                    up,
                    "ls-tree",
                    "-r",
                    "--name-only",
                    sha,
                    f".factory/{entry}",
                ],
                capture_output=True,
                text=True,
            )
            if not r.stdout.strip():
                print(f"  [{kind}] {entry}: 目录在上游不存在（上游整目录已删？清单待退役甄别）", file=sys.stderr)
            for line in r.stdout.splitlines():
                lines.append("%s\t%s" % (kind, line[len(".factory/"):]))
        else:
            lines.append("%s\t%s" % (kind, entry))

    for entry in manifest.get("full", []):
        emit("full", entry)
    for entry in manifest.get("local", {}):
        emit("local", entry)
    return lines


def neutralize_marker(text: str) -> str:
    """破坏文本中的裸标记子串（issue 评论出口的统一防注入）。

    链产正文（回执 reasons、未来任何 LLM 产物）可能从 issue 评论回显
    `[factory:rejected]`（用户以标记表达异议）。state.py 对 issue 评论做
    子串扫描，链评论原样携带即被识别为人工覆盖 → 永久钉死 rejected。
    本函数是**评论出口**（fix-issue.sh issue_comment → sanitize）的唯一
    中和点，渲染器不各自记得。去括号保留语义；循环替换防 `[[...]]`
    嵌套构造替换一次后重组出标记。
    """
    while "[factory:rejected]" in text:
        text = text.replace("[factory:rejected]", "factory:rejected")
    return text

def rejected_reconcile(issues: list[dict]) -> list[dict]:
    """open+factory:rejected issue → 回执存在性 + 人工处置活动对账（纯函数）。

    闭环缺口一（2026-08-23 审计实证）：4 个 rejected issue 的修复已由人工
    feedback PR 吸收进 main，但 issue 仍 open 挂 rejected——链的 reject
    语义是"不修"，reject→人工路径有效但没有回写闭环，"已修未关"只能靠
    人工审计发现。本函数不判定"是否已修复"（语义判断，机器不可判定），
    只暴露处置信号：reject 回执之后的人工评论数（回执幂等 marker 为界）。
    有后续人工评论 = 大概率已处置，提示复核关闭；零评论 = 静默滞留。
    闭环缺口二（2026-09-20 #207 实证）：落标假阴性早退 → 只落标无回执
    ——只落标不发判据是不可审计的静默拒绝（steering 审查报告规范），
    has_receipt=False 即链完整性违规。无回执时不计人工评论（提交/
    裁决前评论 ≠ 处置信号，缺回执本身已是要点名的违规）。
    输出仅报告（dispatch 每轮尾部 echo），不动作——铁律 4：零 LLM 纯 bash
    调用，关闭决策永远归人类。
    """
    out = []
    for it in issues:
        comments = [c for c in (it.get("comments") or [])
                    if isinstance(c, dict)]
        # 回执判据 = 幂等 marker（issue_reject 评论尾埋
        # <!-- factory:receipt:issue-N:r… -->，hosting 两平台均保留注释）：
        # 标题子串可被人工评论复述冒充、屏蔽完整性违规（PR #211
        # Sourcery 评论2）；number 缺失的畸形条目 marker 永不命中 →
        # has_receipt=False（fail-closed 方向）
        marker = f"factory:receipt:issue-{it.get('number')}:r"
        bot_idx = [i for i, c in enumerate(comments)
                   if marker in str(c.get("body") or "")]
        after = comments[(max(bot_idx) + 1):] if bot_idx else []
        # 人工评论 = 有 author 且非 [bot] 后缀（GitHub bot 通用标识）且
        # 非链回执（marker 同上——人工复述标题是真人工活动，应计数）；
        # 缺 author 的畸形条目不计（报告宁少勿多）
        human = [c for c in after
                 if str(c.get("author") or "") and not str(c.get("author")).endswith("[bot]")
                 and marker not in str(c.get("body") or "")]
        out.append({
            "number": it.get("number"),
            "title": str(it.get("title") or "")[:60],
            "has_receipt": bool(bot_idx),
            "human_comments_after_reject": len(human),
        })
    return out


def regression_routing(issue: dict, lease_alive: bool | None = None) -> str:
    """已有 open 回归 issue 的标签态 → 失败结果投递路由（纯函数）。

    L2 滞留接线（2026-09-15 issue #165 实证）：日回归失败复用 open 的
    [factory-regression] issue 时只看标题不看标签态，失败结果会投进
    派发器永久跳过的容器（in-progress 留守 / rejected 死信筒）。
    路由规则（与 fix-issue.sh §7.5 留守语义、dispatch_liveness 第三死法
    同一滞留判据：标签在而租约不活）：
    - factory:in-progress 在标：
      - lease_alive is False（滞留：零改动轮留守 / 链早亡）→ "wake"：
        留守是防"已验证诉求"被重派，新失败 ≠ 同一诉求，移除
        in-progress 唤醒重派（容器复用）；
      - lease_alive 为 True（修复链在途）→ "live"：只评论追加不唤醒
        ——剥掉存活链的 in-progress 会使 §7.5 留守对该轮失效（审查
        major：同一概念两种判据的矛盾，2026-09-16 修复）；
      - lease_alive 为 None（形态未知：PG 租约在库中 / 判定失败）→
        "live"：保守不自动唤醒，人工处置（与 liveness 降级一致）。
    - factory:rejected 在标 → "new"：人工已判噪音，新失败不得进人工
      已拒容器，开新 issue 承载（旧容器不动，拒裁不推翻）；
    - 其余（零标签待 triage / in-review / needs-human）→ "append"：
      原样追加——in-review 有 PR 评审面、needs-human 本就等人看。
    in-progress 与 rejected 互斥（状态机单请求原子换标），若数据异常
    并存，wake/live 优先（可自动处置的路由优先）。
    """
    labels = set(issue.get("labels") or [])
    # Sourcery 目标形态叠加：lift-return-into-if（return 提入分支）×
    # assign-if-exp（if/else-return 化三元）——elif 链各分支直接 return、
    # 内层用三元、无尾随语句（PR #192 门禁第四轮）
    if "factory:in-progress" in labels:
        return "wake" if lease_alive is False else "live"
    elif "factory:rejected" in labels:
        return "new"
    else:
        return "append"


RECEIPT_CLOSURE_NOTE = (
    "> 处置协议：走人工 PR 修复本 issue 时，PR 描述请带 `Closes #<编号>`"
    "——合并即自动关闭，避免「已修未关」滞留（reject→人工路径的闭环盲区）。"
)


def reject_receipt(triage: dict) -> str:
    """triage 裁决（reject）→ 拒绝回执 markdown（五段式：结论/依据/指引/关联/边界）。

    确定性渲染，零 LLM（链脚本纪律，铁律 4 同源）。安全不变量不在本函数：
    标记中和统一在评论出口（issue_comment → factory_lib sanitize）执行，
    渲染器管内容、出口管安全——本函数原样渲染 reasons（可能含标记）。
    rejected 的机器状态由标签承载，人类审计由回执承载；标记评论通道
    保留给人类手动覆盖（人写人删，state.py 语义）。
    """
    raw = triage.get("reasons")
    reasons = raw if isinstance(raw, list) else []  # 标量/缺失 → 空，不抛 TypeError
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
            failed.add(m[1])
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
        RECEIPT_CLOSURE_NOTE,
        "",
    ]
    return "\n".join(lines)

# ═════════════════════════════════════════════════════════════════════
# dispatch 进程编排（2026-08-24 自 dispatch.sh 下沉，docs/adr/ADR-005-dispatch-orchestration-python.md）
#
# 动机：ADR-002 记账的缺陷类——jobs 表/wait 落空（0d947f60）、管道吞码
# （61c119c2）、管道早退（a4d81930）、trap 吞错（c749ac5e）——全部是
# bash 进程原语的边角语义。子进程句柄收敛到本模块后，该类缺陷
# 在结构上不可表达：Popen 对象即作业表，poll 即收割，returncode 可观测。
# dispatch.sh 退为入口 shim，CLI/env/退出码契约逐项等价。
# ═════════════════════════════════════════════════════════════════════


class ChainPool:
    """链并发槽：spawn 占槽（满则阻塞让位），wait_all 收割全部。

    bash 时代的「后台链不进 job 表致 wait 落空」（0d947f60）与
    `jobs -rp | wc -l` 竞态清点在此结构性消灭。
    """

    def __init__(self, factory: Path, max_parallel: int, poll_secs: float = 5.0):
        # 防御性校验（PR #53 审查②）：0/负并发使 spawn 的槽满等待永久为真，
        # 调度挂起而非配置错误——直接拒绝构造。
        if max_parallel < 1:
            raise ValueError(
                f"max_parallel 须为正整数（得到 {max_parallel}）——0/负值使并发槽永久等待")
        self.factory = factory
        self.max_parallel = max_parallel
        self.poll_secs = poll_secs
        self._active: list[tuple[int, subprocess.Popen]] = []
        self.done: list[tuple[int, int]] = []  # (issue, returncode) 收割记录

    def _reap(self) -> None:
        for n, p in self._active:
            if p.poll() is not None:
                self.done.append((n, p.returncode))
        self._active = [(n, p) for n, p in self._active if p.poll() is None]

    def spawn(self, issue: int) -> None:
        """占并发槽运行链。FACTORY_DISPATCHED=1：链知道锁已由父持有，
        S1 手动互斥锁免获取（防自锁）。日志尾追 artifacts/issue-N/dispatch.log，
        父目录先建——bash `>>` 对缺目录静默死链是既证缺陷形态。"""
        log_dir = self.factory / "artifacts" / f"issue-{issue}"
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / "dispatch.log", "ab")
        try:
            proc = subprocess.Popen(
                ["bash", str(self.factory / "fix-issue.sh"), str(issue)],
                stdout=log, stderr=subprocess.STDOUT,
                env={**os.environ, "FACTORY_DISPATCHED": "1"})
        finally:
            log.close()
        self._active.append((issue, proc))
        while len(self._active) >= self.max_parallel:  # 槽满让位（对齐 bash 轮询节奏）
            time.sleep(self.poll_secs)
            self._reap()

    def wait_all(self) -> None:
        while True:
            self._reap()
            if not self._active:
                return
            time.sleep(self.poll_secs)

    def shutdown(self, grace: float = 10.0) -> list[int]:
        """终止并收割活跃链（TERM/HUP 出口的对应物，PR #53 审查④）。

        孤儿链会在锁释放后与新 dispatcher 并发，故必须先收尸再放锁：
        先全体 SIGTERM，限期内收割，逾期 SIGKILL 兜底。返回未在限期内
        自行退出的 issue 号列表（尽力语义，正常路径 wait_all 后为空）。
        """
        for _n, p in self._active:
            if p.poll() is None:
                p.terminate()
        deadline = time.monotonic() + grace
        while self._active and time.monotonic() < deadline:
            self._reap()
            if self._active:
                time.sleep(self.poll_secs)
        stuck: list[int] = []
        for n, p in self._active:
            try:
                p.kill()
                p.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            stuck.append(n)
        self._active = []
        return stuck


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在但非属主；bash kill -0 同样 EPERM 却按死接管——此处取 POSIX 正确语义
    except ValueError:
        return False  # 垃圾 pid：kill -0 报错，bash 语义按死处理


def acquire_dispatch_lock(lock_dir: Path, pid: int) -> bool:
    """双实例硬锁：mkdir 原子占锁 + PID 活性检测（macOS 无 flock(1)）。

    锁挂主树 .factory（调用方以 git-common-dir 锚定，39b6b8ec：worktree
    隔离后各树 locks/ 互不可见，锁随树走会绕开互斥）；父目录预建——父缺
    ENOENT 会被误读为「另一 dispatcher 运行中」（源仓 PR#79）。
    cron 重叠是常态：忙时返回 False，调用方 exit 0。
    """
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_dir.mkdir()
    except FileExistsError:
        old = ""
        try:
            old = (lock_dir / "pid").read_text(encoding="ascii").strip()
        except (OSError, ValueError):
            pass
        alive = False
        if old:
            try:
                alive = _pid_alive(int(old))
            except ValueError:
                alive = False
        if old and not alive:
            print(f"锁持有者 pid={old} 已死，接管陈锁", file=sys.stderr)
            shutil.rmtree(lock_dir, ignore_errors=True)
            try:
                lock_dir.mkdir()
            except FileExistsError:
                print("另一 dispatcher 运行中，退出", file=sys.stderr)
                return False
        else:
            print(f"另一 dispatcher 运行中（pid={old}），退出", file=sys.stderr)
            return False
    (lock_dir / "pid").write_text(str(pid), encoding="ascii")
    return True


def release_dispatch_lock(lock_dir: Path) -> None:
    """放锁（幂等）。bash EXIT trap 的对应物；TERM/HUP 处理器转 SystemExit
    保证 finally 路径执行。"""
    shutil.rmtree(lock_dir, ignore_errors=True)


# （slug 解析已迁 hosting.py——平台选择逻辑归抽象层，ADR-008）


_PRIORITY_RANK = {"priority:critical": 0, "priority:high": 1,
                  "priority:medium": 2, "priority:low": 3}


def sort_by_priority(issues: list[dict]) -> list[int]:
    """accepted issue 号按 priority:* 排序（critical>high>medium>low；
    无 priority 垫底，同 rank 按号升序）。labels 为中立 [str]。"""
    rows = sorted(
        (min((_PRIORITY_RANK.get(l, 9) for l in i["labels"]), default=9),
         i["number"])
        for i in issues)
    return [n for _, n in rows]


def approved_prs(prs: list[dict]) -> list[tuple[int, bool]]:
    """open+factory:approved PR → (number, mergeable)，中立 review 字段。"""
    return [(int(p["number"]), bool(p["mergeable"])) for p in prs
            if p["review"] == "approved"]


class _DispatchCfg:
    def __init__(self, factory: Path, main_factory: Path, adapter, dry: bool):
        self.factory = factory
        self.main_factory = main_factory
        self.adapter = adapter  # hosting 适配器实例（ADR-008）
        self.dry = dry
        self.max_parallel = int(os.environ.get("MAX_PARALLEL") or 4)
        self.merge_method = os.environ.get("FACTORY_MERGE_METHOD") or "merge"
        # auto-merge 受 A5 门控：FACTORY_AUTO_MERGE=1 且 metrics/auto-merge-unlocked
        # 存在（mutations kill-rate ≥80% 前不得开启——「未证明的门不是门」）
        self.auto_merge = (os.environ.get("FACTORY_AUTO_MERGE") == "1"
                           and (factory / "metrics" / "auto-merge-unlocked").is_file())
        self.pool = ChainPool(factory, self.max_parallel)

    def say(self, msg: str) -> None:
        print(("  [dry-run] " if self.dry else "  ") + msg)


def _hosting_json(cfg: _DispatchCfg, what: str, fn):
    """hosting 查询；瞬断/输出异常 → 可诊断跳过该批（对齐 triage 批次
    c22130df 的降级形态：失败可见，不静默也不炸轮）。"""
    try:
        return fn()
    except hosting.HostingError as e:
        # 失败必须有痕（PR #53 审查⑤）：平台故障/权限失败若无告警，
        # 空队列会被当成「无事可做」，整轮静默空转还报成功。
        print(f"  [warn] hosting {what} 失败（{e}），跳过该批"
              "——若是持续故障请检查平台凭据/网络", file=sys.stderr)
        return []


def _claim(cfg: _DispatchCfg, n: int) -> bool:
    """消费 accepted → in-progress（幂等重试 ×2，add+remove 单请求——
    GitHub 换标签非 CAS，见 README「S2 落地记录」1；ADR-008 起走 hosting）。"""
    if cfg.dry:
        cfg.say(f"claim issue #{n}: accepted → in-progress")
        return True
    for _ in range(2):
        try:
            cfg.adapter.issue_set_labels(
                n, add=["factory:in-progress"], remove=["factory:accepted"])
            return True
        except hosting.HostingError:
            continue
    print(f"  claim #{n} 失败（并发或权限），跳过", file=sys.stderr)
    return False


def _pr_link_issue(cfg: _DispatchCfg, pr_number: int) -> str:
    """PR body → 关联 issue 号（Closes #N 解析权威在 state.py link）。"""
    try:
        body = cfg.adapter.pr_view(pr_number)["body"]
    except hosting.HostingError:
        return ""
    r = subprocess.run([sys.executable, str(cfg.factory / "state.py"),
                        "link", "/dev/stdin"],
                       input=json.dumps({"body": body}), capture_output=True,
                       text=True)
    return r.stdout.strip()


def _issue_in_progress(cfg: _DispatchCfg, n: int) -> bool:
    """D4（2026-08-21 双派实证）：平台 label 过滤是「含有」非「仅有」，
    accepted+in-progress 双标签条目仍在队列，必须显式跳过在跑的。"""
    try:
        return "factory:in-progress" in cfg.adapter.issue_labels(n)
    except hosting.HostingError:
        return False


def _run_breaker_gate(cfg: _DispatchCfg) -> int:
    """R4 成本熔断：每轮派发前检查（DRY 干跑无副作用不检查）。透传 breaker.sh
    退出码（3=熔断；1=floor 缺失/损坏 fail-closed）。锁路径对齐硬锁：
    git-common-dir 锚定主树，worktree 内启动也能读到主台账。"""
    if cfg.dry:
        return 0
    return subprocess.run(["bash", str(cfg.factory / "breaker.sh"),
                           str(cfg.main_factory / "locks")]).returncode


def _run_state_sync(cfg: _DispatchCfg) -> None:
    """轮首全量 state 快照（factory-state.sh sync --all）。"""
    cfg.say("sync: factory-state.sh sync --all")
    if not cfg.dry:
        subprocess.run(["bash", str(cfg.factory / "factory-state.sh"),
                        "sync", "--all"])


def _triage_batch(cfg: _DispatchCfg) -> None:
    """零标签 issue 裁决批次（triage-batch.sh）；失败不阻断派发。"""
    print("-- triage 批次（零标签 issue 裁决；失败不阻断派发） --")
    if cfg.dry:
        cfg.say("triage-batch: 零 factory 标签 issue，≤MAX_TRIAGE 个")
    else:
        rc = subprocess.run(["bash", str(cfg.factory / "triage-batch.sh")]).returncode
        print(f"-- triage 批次结束（exit={rc}） --")


def _handle_approved_prs(cfg: _DispatchCfg) -> None:
    """approved：sync 已打好标签；此处只做 A5 门内的 merge 动作。"""
    print("-- PR 结果处理（优先） --")
    for num, mergeable in approved_prs(_hosting_json(
            cfg, "pr list(approved)",
            lambda: cfg.adapter.pr_list(state="open", label="factory:approved",
                                        limit=50))):
        if cfg.auto_merge and mergeable is True:
            try:
                cfg.adapter.pr_merge(num, method=cfg.merge_method)
                print(f"  PR #{num} 已合并；issue 由平台自动关闭")
            except hosting.HostingError as e:
                print(f"  [warn] PR #{num} merge 失败: {e}", file=sys.stderr)
        else:
            print(f"  PR #{num} approved 但 A5 门未开（FACTORY_AUTO_MERGE + metrics/auto-merge-unlocked）→ 人工合并")


def _redispatch_needs_fix(cfg: _DispatchCfg) -> None:
    """needs-fix PR → 关联 issue 重派（remove needs-fix 保计数活性）。"""
    print("-- needs-fix 重派（计数契约：claim 时移除 needs-fix） --")
    # 计数契约：重派必须 remove factory:needs-fix——label 事件只在添加时
    # 触发，标签滞留则 state.py 轮次计数冻结（test_state.py 有边界测试）
    for pr in _hosting_json(cfg, "pr list(needs-fix)",
                            lambda: cfg.adapter.pr_list(
                                state="open", label="factory:needs-fix",
                                limit=50)):
        p = pr["number"]
        n = _pr_link_issue(cfg, p)
        if not n:
            print(f"  PR #{p} 无关联 issue（body 缺 Closes #N），跳过", file=sys.stderr)
            continue
        if _issue_in_progress(cfg, int(n)):
            print(f"  issue #{n} 已 in-progress，跳过")
            continue
        cfg.say(f"PR #{p} → issue #{n} 重派（remove needs-fix 保计数活性）")
        if not cfg.dry:
            try:
                cfg.adapter.pr_set_labels(p, remove=["factory:needs-fix"])
            except hosting.HostingError as e:
                print(f"  [warn] PR #{p} 移除 needs-fix 失败: {e}", file=sys.stderr)
                continue
        if _claim(cfg, int(n)):
            cfg.pool.spawn(int(n))


def _drain_accepted_queue(cfg: _DispatchCfg) -> None:
    """accepted 队列按 priority 排序消费 → 派链（并发 ≤ max_parallel）。"""
    print(f"-- accepted 队列（priority 排序，并发 ≤{cfg.max_parallel}） --")
    for n in sort_by_priority(_hosting_json(
            cfg, "issue list(accepted)",
            lambda: cfg.adapter.issue_list(state="open", label="factory:accepted",
                                           limit=100))):
        if _issue_in_progress(cfg, n):
            print(f"  issue #{n} 已 in-progress，跳过")
            continue
        if _claim(cfg, n):
            cfg.say(f"issue #{n} → 链")
            cfg.pool.spawn(n)


def _final_sync(cfg: _DispatchCfg) -> None:
    """等链收尾：本轮链全部退出后再次全量 state sync。"""
    if not cfg.dry:
        cfg.pool.wait_all()
        print("本轮链全部结束，收尾 sync")
        subprocess.run(["bash", str(cfg.factory / "factory-state.sh"),
                        "sync", "--all"])


def _reconcile_rejected(cfg: _DispatchCfg) -> None:
    """rejected 存量对账（reject→人工闭环缺口，2026-08-23 审计；
    2026-09-20 #207 补回执存在性）。只报告不动作（铁律 4）：缺回执的 →
    点名补发（链完整性违规）；有 reject 后人工评论的 → 提示复核关闭；
    零评论的 → 静默滞留计数。关闭决策永远归人类。"""
    for r in rejected_reconcile(_hosting_json(
            cfg, "issue list(rejected)",
            lambda: cfg.adapter.issue_list(state="open", label="factory:rejected",
                                           limit=100, comments=True))):
        c, t = r["human_comments_after_reject"], r["title"]
        if not r["has_receipt"]:
            print(f"  [rejected] #{r['number']} 缺回执评论（只落标不发判据 = "
                  f"不可审计的静默拒绝，#207 同型）——需补发（{t}）")
        elif c > 0:
            print(f"  [rejected] #{r['number']} 裁决后有 {c} 条人工评论——已处置？复核关闭（{t}）")
        else:
            print(f"  [rejected] #{r['number']} 静默滞留（无后续人工评论，{t}）")


def _upstream_sync_check(cfg: _DispatchCfg) -> int:
    """M2 上游同步检查（设计 §11.2）：零 LLM、不占 R4 预算。
    不复用 fix-issue 链（guard PERIMETER 含 .factory/，链按设计拦工具链
    自变更）；exit 0 = 同步已推进 → 当轮即止（自我指涉护栏：后续派发仍跑
    内存旧脚本，下一轮生效）；1/2/3 不阻断本轮派发。

    根仓免跑（2026-09-05 裁决：本仓库是根仓、无上游）：锁文件缺
    upstream 字段 = 无上游声明 → 直接跳过，不再触发脚本 exit 2 噪音
    （此前 103 轮 dispatch 日志刷「缺 upstream 字段」）。fork 侧
    sync --apply 写锁带 upstream=根仓 URL → 走正常检查自动追平。"""
    check = cfg.factory / "upstream-sync-check.sh"
    lock = cfg.factory / "upstream-lock.json"
    if os.access(check, os.X_OK) and lock.is_file():
        try:
            payload = json.loads(lock.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("upstream-lock.json must contain an object")
            declared = payload.get("upstream")
        except (OSError, ValueError):
            print("（upstream-lock.json 不可读或非对象——跳过上游同步，需人工处置）")
            return 0
        if not declared and not os.environ.get("FACTORY_UPSTREAM"):
            print("（根仓无上游声明，免上游同步——fork 侧仍自动追平）")
            return 0
        if subprocess.run(["bash", str(check)]).returncode == 0:
            print("上游同步已推进，本轮派发即止（下轮生效）")
            return 0
        print("（upstream-sync 未推进，继续本轮派发）")
    return 0


def dispatch_round(cfg: _DispatchCfg) -> int:
    """单轮：breaker 门 → sync → triage 批次 → PR 结果 → needs-fix 重派 →
    accepted 队列 → 等链收尾 sync → rejected 对账 → M2 上游同步检查。
    唯一非零返回 = 熔断/门故障透传码（watch 循环据此一并停摆）。"""
    print(f"=== dispatch @ {datetime.datetime.now():%H:%M:%S} ===")
    rc = _run_breaker_gate(cfg)  # R4 熔断门：非零透传，watch 停摆
    if rc != 0:
        return rc
    _run_state_sync(cfg)
    _triage_batch(cfg)
    _handle_approved_prs(cfg)
    _redispatch_needs_fix(cfg)
    _drain_accepted_queue(cfg)
    _final_sync(cfg)
    _reconcile_rejected(cfg)
    return _upstream_sync_check(cfg)


def _parse_dispatch_args(args: list[str]) -> tuple[bool, float, bool]:
    """CLI/env 参数解析 → (watch, interval, dry)。--dry-run（DRY=1 同义，
    2026-08-21 事故教训：两者都认）/ --watch / --interval N（INTERVAL 环境
    变量同义，默认 300s）。"""
    watch = False
    interval = float(os.environ.get("INTERVAL") or 300)
    dry = os.environ.get("DRY", "0") == "1"
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--dry-run":
            dry = True
        elif a == "--watch":
            watch = True
        elif a == "--interval" and i + 1 < len(args):
            interval = float(args[i + 1])
            i += 1
        i += 1
    return watch, interval, dry


def _run_dispatch_loop(cfg: _DispatchCfg, watch: bool, interval: float) -> int:
    """watch 常驻循环 / 单轮执行；非零 rc 透传（watch 一并停摆）。"""
    if watch:
        while True:
            rc = dispatch_round(cfg)
            if rc != 0:
                return rc  # 熔断/门故障：watch 一并停摆（bash exit $? 语义）
            time.sleep(interval)
    rc = dispatch_round(cfg)
    if not cfg.dry:
        print("提示: --watch 常驻（或 cron */30 调用单轮）")
    return rc


def dispatch_main(args: list[str]) -> int:
    """dispatch.sh shim 的实现体。CLI/env 契约与 bash 版逐项等价：
    --dry-run（DRY=1 同义，2026-08-21 事故教训：两者都认）/ --watch /
    --interval N（INTERVAL 环境变量同义，默认 300s：链首 triage 批次 30s
    级、全链分钟级，30min 轮询让新 issue 平均等 15min）。"""
    watch, interval, dry = _parse_dispatch_args(args)
    # MAX_PARALLEL 配置错误 fail-fast（PR #53 审查②）：0/负/非整数值会让
    # ChainPool 槽满等待永久为真——挂起而非报错。config-error = 退出码 2。
    # 前置于 git/gh/slug 环境探测：纯 env 校验与仓库环境无关，配置错误
    # 的报错不应被 slug 解析失败遮蔽（测试环境无 github remote 时先红错处）。
    mp_raw = os.environ.get("MAX_PARALLEL") or "4"
    try:
        int(mp_raw)
    except ValueError:
        print(f"MAX_PARALLEL 非整数: {mp_raw!r}", file=sys.stderr)
        return 2
    if int(mp_raw) < 1:
        print(f"MAX_PARALLEL 须为正整数（得到 {mp_raw!r}）", file=sys.stderr)
        return 2

    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # 诊断附着（2026-08-27 bare 事故：笼统消息掩盖 core.bare=true 8 小时）
        bare = subprocess.run(["git", "config", "core.bare"],
                              capture_output=True, text=True).stdout.strip()
        print(f"不在 git 仓库（诊断: core.bare={bare or '?'}）", file=sys.stderr)
        return 2
    repo = Path(r.stdout.strip())
    factory = repo / ".factory"
    try:
        adapter = hosting.current_adapter(repo)
    except hosting.HostingError as e:
        print(f"托管平台配置错误: {e}", file=sys.stderr)
        return 2
    if adapter.name == "github" and not adapter.slug():
        print("无法确定 GitHub 仓库 slug", file=sys.stderr)
        return 2
    if not adapter.auth_ok():
        print("托管平台不可用（hosting auth：gh 凭据或云效令牌）", file=sys.stderr)
        if diag := getattr(adapter, "auth_diagnose", lambda: "")():
            # 留痕可回溯（2026-09-05 02:00 事故：auth_ok 失败细节被丢弃）
            print(f"hosting auth 诊断: {diag}", file=sys.stderr)
        return 2
    # 主树锚定：git-common-dir 在 worktree 中指向主 .git，据此回到主树
    # .factory（39b6b8ec 硬锁语义）；非 git 环境退回 CWD 仓 .factory
    g = subprocess.run(["git", "rev-parse", "--path-format=absolute",
                        "--git-common-dir"], capture_output=True, text=True)
    main_factory = factory
    if g.returncode == 0 and g.stdout.strip():
        main_factory = Path(g.stdout.strip().removesuffix("/.git")) / ".factory"

    cfg = _DispatchCfg(factory, main_factory, adapter, dry)
    lock_dir = main_factory / "locks" / "dispatcher"
    if not acquire_dispatch_lock(lock_dir, os.getpid()):
        return 0  # cron 重叠是常态非错误（bash: acquire_lock || exit 0）
    for sig in (signal.SIGTERM, signal.SIGHUP):
        # EXIT trap 对应物：TERM/HUP → SystemExit 走 finally 放锁
        signal.signal(sig, lambda s, _f: sys.exit(128 + int(s)))
    try:
        return _run_dispatch_loop(cfg, watch, interval)
    finally:
        if stuck := cfg.pool.shutdown():
            print(f"  [warn] {len(stuck)} 条链未限期退出已 SIGKILL: {stuck}",
                  file=sys.stderr)
        release_dispatch_lock(lock_dir)


# ═════════════════════════════════════════════════════════════════════
# 并行测试门编排（ADR-016：自宿主仓门禁脚本下沉，能力随 full 面分发）
#
# 动机与 ADR-005 同型：段 fan-out（后台任务表/两轮 wait/按序回放/失败
# 聚合/日志保留）长期驻留宿主仓的 bash 门禁脚本，能力无法到达下游
# java/php/dotnet/go 等多语言仓。下沉本模块后：编排一次实现，
# DISTRIBUTION full 面零新增文件即达全部下游；段清单/并发上限/段内
# 并行档 = 数据（factory-local.json parallel_gate 可选键，缺省不启用
# ——未采用下游零行为变化）；语言适配表 = 代码（保守档：fork 级分发，
# 无进程内线程交错）。bash 边角语义类缺陷（wait 落空/管道吞码/trap
# 吞错，ADR-002 记账）在新消费方结构上不可表达。
# ═════════════════════════════════════════════════════════════════════


def detect_stack(root: Path) -> str | None:
    """构建文件探测 → 测试栈 id（best-effort；段配置 stack 显式指定优先）。

    覆盖 full 面下游语言谱系（java/gradle/go/rust/php/dotnet/js/
    python），构建系统标记优先于包管理器标记，多语言混合目录取第一
    命中。未命中 → None：段内并行档自动降级串行并提示（见
    intra_parallel_args），不猜。
    """
    if (root / "pom.xml").is_file() or (root / "mvnw").is_file():
        return "maven"
    for m in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
        if (root / m).is_file():
            return "gradle"
    if (root / "go.mod").is_file():
        return "go"
    if (root / "Cargo.toml").is_file():
        return "cargo"
    for m in ("phpunit.xml", "phpunit.xml.dist"):
        if (root / m).is_file():
            return "phpunit"
    if any(root.glob("*.csproj")) or any(root.glob("*.sln")):
        return "dotnet"
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            d = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        deps = {*(d.get("dependencies") or {}), *(d.get("devDependencies") or {})}
        test_cmd = str((d.get("scripts") or {}).get("test") or "")
        if "vitest" in deps or "vitest" in test_cmd:
            return "vitest"
        if "jest" in deps or "jest" in test_cmd:
            return "jest"
    if (root / "pytest.ini").is_file() or (root / "conftest.py").is_file():
        return "pytest"
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and "[tool.pytest" in pyproject.read_text(
            encoding="utf-8", errors="replace"):
        return "pytest"
    return None


def _xdist_available(py: str) -> bool:
    """pytest-xdist 软依赖探测（缺席 → 段内串行 + ℹ️ 提示，不炸门）。"""
    return subprocess.run([py, "-c", "import xdist"], capture_output=True).returncode == 0


def intra_parallel_args(stack: str | None, py: str) -> tuple[list[str], str | None]:
    """测试栈 → 段内并行 argv 后缀 + 观测提示行（保守档，ADR-016）。

    保守档原则：只注入「模块级/fork 级分发」参数——测试类分布到并行
    单元、单元内保持串行；不注入进程内线程交错类参数（如 Maven
    -Dparallel=methods 这类顺序敏感放大器）。框架默认已并行的栈零附加
    参数（诚实声明，不重复计功）；无保守参数可注的栈同样声明而非
    硬凑。顺序敏感测试所在段的逃生舱 = 段级 intra:off（显式回退串行）。
    """
    if stack == "pytest":
        if _xdist_available(py):
            return ["-n", "auto"], None
        return [], "未装 pytest-xdist：pytest 段内串行降级（pip install pytest-xdist 提速）"
    if stack == "maven":
        # -T 1C 模块级并行；forkCount=1C 测试类跨 fork 分发 +
        # reuseForks 复用 JVM——类内方法仍串行（Surefire 保守档）
        return ["-T", "1C", "-DforkCount=1C", "-DreuseForks=true"], None
    if stack == "gradle":
        # 任务级并行。测试 fork 并行（maxParallelForks）是构建脚本面，
        # CLI 无保守注入点——需要时在仓内 build 配置
        return ["--parallel"], None
    if stack == "jest":
        return ["--maxWorkers=50%"], None
    if stack in ("vitest", "go", "cargo"):
        return [], f"{stack} 默认已并行（进程/包/线程池内建），无附加参数"
    if stack in ("phpunit", "dotnet"):
        return [], f"{stack} 无 CLI 保守并行参数（paratest / xunit.runner.json 属仓面配置），段内串行"
    return [], "未识别测试栈：段内串行（段配置 stack 显式指定可启用并行档）"


# 中断清理限宽：SIGTERM 后最多等这么久，仍存活的段进程组 SIGKILL 收尾
_TERM_GRACE_SECS = 5.0


def _kill_group(pgid: int, sig: int) -> None:
    """向段进程组发信号；组已消失（已退出/已收割）则静默——清理不放大异常。"""
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass

def _seg_log_path(log_dir: Path, i: int, tag: str) -> Path:
    """段日志路径：序号前缀保回放序可读；tag 清洗禁路径分隔符。"""
    return log_dir / f"{i:02d}-{tag.replace('/', '__')}.log"


def run_parallel_gate(
    repo_root: Path | None = None,
    cfg: dict | None = None,
    failed_tags_path: str | None = None,
) -> int:
    """执行并行测试门：段 fan-out + 可选有界并发 + 按配置序回放。

    返回 0=全绿 / 1=段失败 / 2=配置错误（fail-closed，不产出裁决）。
    段日志私有化于 tempfile.mkdtemp（尊重 TMPDIR）：全绿即删；失败保留
    并打印路径（事后取证语义对齐宿主仓门禁脚本的段日志保留）。回放
    序=配置段序、与完成序解耦——输出 diff 稳定，先完成的段不抢跑。
    失败段 tag 逐行写 failed_tags_path（供宿主脚本聚合串行段失败后一次
    裁决；无失败=空文件）。workers=0 不限并发（缺省），>0 有界槽位
    轮转（CI 资源受限仓的节流面）。段独立进程组（start_new_session）
    执行；中断（BaseException）按组收尸：SIGTERM → 限宽等待 → SIGKILL
    → 收割直接子进程，段日志保留取证，原始异常照抛（PR #220 评论）。
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parent.parent
    if cfg is None:
        # 损坏配置 RuntimeError 在此转 rc 2（PR #220 评论）：宿主脚本仅
        # 对 2 走 fail-closed 立即终止，traceback（rc 1）会漏进普通段
        # 失败路径
        try:
            cfg = parallel_gate_cfg()
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 2
    if cfg is None:
        print("未配置 parallel_gate（可选键缺失），无并行门可执行", file=sys.stderr)
        return 2
    py = os.environ.get("PYTHON") or "python3"

    # 执行前预算：cwd 存在性 + intra 档解析 + 注记去重（原子性：任何段
    # 配置错误在 spawn 前拦截，不产生半跑状态——对齐 fail-closed 范式）
    suffixes: list[list[str]] = []
    notes: list[str] = []
    for seg in cfg["segments"]:
        cwd = root / seg.get("cwd", ".")
        if not cwd.is_dir():
            print(f"段 {seg['tag']}: cwd 不存在: {cwd}", file=sys.stderr)
            return 2
        if "argv" in seg and seg.get("intra", "off") == "auto":
            suffix, note = intra_parallel_args(seg.get("stack") or detect_stack(cwd), py)
            suffixes.append(suffix)
            if note and note not in notes:
                notes.append(note)
        else:
            suffixes.append([])
    for n in notes:
        print(f"ℹ️ {n}")

    segs = cfg["segments"]
    log_dir = Path(tempfile.mkdtemp(prefix="factory-parallel-gate."))
    rcs: list[int | None] = [None] * len(segs)
    failed: list[str] = []
    running: list[tuple[int, subprocess.Popen]] = []   # try 外可见：异常清理要收它
    try:
        pending = list(range(len(segs)))
        workers = cfg["workers"]
        while pending or running:
            while pending and (workers == 0 or len(running) < workers):
                i = pending.pop(0)
                seg = segs[i]
                if "argv" in seg:
                    words = [py if w == "$PY" else w for w in seg["argv"]] + suffixes[i]
                else:
                    # shell 段：bash -c 名义参数 "_" 占 $0、解释器进 $1
                    # （宿主脚本 $PY 占位约定的等价面）；pipefail 保管道
                    # 段退出码真实（吞码缺陷类，ADR-002 记账）
                    words = ["bash", "-o", "pipefail", "-c", seg["shell"], "_", py]
                # 独立进程组（会话组长，pgid=pid）：中断清理 killpg 收整组，
                # 段的测试后代（xdist worker 等）不残留为孤儿
                with open(_seg_log_path(log_dir, i, seg["tag"]), "wb") as log_fh:
                    running.append((i, subprocess.Popen(
                        words, cwd=str(root / seg.get("cwd", ".")),
                        stdout=log_fh, stderr=subprocess.STDOUT,
                        start_new_session=True)))
            still: list[tuple[int, subprocess.Popen]] = []
            for i, p in running:
                if (rc := p.poll()) is None:
                    still.append((i, p))
                else:
                    rcs[i] = rc
            running = still
            if running:
                time.sleep(0.05)

        for i, seg in enumerate(segs):
            print(f"── {seg.get('name') or seg['tag']}")
            text = _seg_log_path(log_dir, i, seg["tag"]).read_text(
                encoding="utf-8", errors="replace")
            sys.stdout.write(text if not text or text.endswith("\n") else text + "\n")
            print()
            if rcs[i] != 0:
                failed.append(seg["tag"])
    except BaseException:
        # 中断（KeyboardInterrupt/信号）也要让取证路径可观测，不留哑尸体：
        # 逐组 SIGTERM → 限宽等待 → SIGKILL → 收割直接子进程。限宽窗内的
        # 二次中断与超时同路（升级 SIGKILL），清理异常不外抛、不覆盖原始异常
        print(f"⚠️ 并行门中断，段日志保留: {log_dir}", file=sys.stderr)
        for _i, p in running:
            _kill_group(p.pid, signal.SIGTERM)
        deadline = time.monotonic() + _TERM_GRACE_SECS
        for _i, p in running:
            try:
                p.wait(timeout=max(0.0, deadline - time.monotonic()))
            except BaseException:   # TimeoutExpired 与限宽窗内二次中断同路：升级收割
                _kill_group(p.pid, signal.SIGKILL)
                try:
                    p.wait()
                except OSError:
                    pass
        raise
    if failed_tags_path is not None:
        Path(failed_tags_path).write_text(
            "".join(f"{t}\n" for t in failed), encoding="utf-8")
    if failed:
        print(f"❌ 失败段: {' '.join(failed)}")
        print(f"❌ 段日志保留: {log_dir}", file=sys.stderr)
        return 1
    shutil.rmtree(log_dir, ignore_errors=True)
    print(f"✅ 并行段 {len(segs)}/{len(segs)} 全绿")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "dispatch":
        # dispatch [--dry-run] [--watch] [--interval N] —— S2 派发器
        return dispatch_main(argv[2:])
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
    if cmd == "rejected-reconcile":
        # rejected-reconcile < issues.json —— dispatch 尾部对账报告（TSV:
        # number \t human_comments \t title）。见 rejected_reconcile
        for r in rejected_reconcile(json.load(sys.stdin)):
            print(f"{r['number']}\t{r['human_comments_after_reject']}\t{r['title']}")
        return 0
    if cmd == "regression-routing":
        # regression-routing [alive|dead|unknown] < issue.json —— 日回归
        # 失败投递路由（wake|live|new|append，见 regression_routing）；
        # alive/dead/unknown = 滞留 issue 的租约存活态（调用方经
        # lease-fresh 判定），缺省 unknown（保守不唤醒）
        state = {"alive": True, "dead": False}.get(argv[2] if len(argv) > 2
                                                   else "unknown")
        print(regression_routing(json.loads(sys.stdin.read()), state))
        return 0
    if cmd == "lease-fresh":
        # lease-fresh <lock-path> —— 单写者锁文件存活判定：内容第 5 字段
        # = 租期秒（缺省回退 900），mtime+租期 > now = 活；文件缺失/
        # 不可读/内容畸形 = 死（SIGKILL 残锁过期同判）。退出码 0=活 1=死
        # 2=参数错。PG 形态（SUPABASE_DB）租约在库中，调用方不得用本
        # 命令的输出断言死活（保守 unknown）。
        lock = Path(argv[2])
        try:
            line = lock.read_text(encoding="utf-8").strip().splitlines()[0]
        except (OSError, IndexError):
            return 1
        parts = line.split("|")
        # 回退链对齐权威 _lease_sw_fresh（factory-lease.sh:118）：
        # 第5字段缺 → FACTORY_LEASE_SECS env → 900
        fallback = os.environ.get("FACTORY_LEASE_SECS", "900")
        fallback = fallback if fallback.isdigit() else "900"
        secs = parts[4] if len(parts) > 4 and parts[4].isdigit() else fallback
        try:
            mtime = lock.stat().st_mtime
        except OSError:
            return 1
        return 0 if mtime + int(secs) > time.time() else 1
    if cmd == "sanitize":
        # sanitize <file>... —— 评论出口标记中和：原地写回（无变化则跳过，
        # 幂等）。issue_comment 发送前必经；详见 neutralize_marker
        for p in argv[2:]:
            path = Path(p)
            text = path.read_text(encoding="utf-8")
            fixed = neutralize_marker(text)
            if fixed != text:
                path.write_text(fixed, encoding="utf-8")
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
        # NUL 分隔（PR #116 CodeRabbit）：套件名可含空格（skills/foo bar/...），
        # 换行 + shell for 词拆分（$(...) 去换行按 IFS 切）会拆碎名、静默跳过
        # 证据段；消费端（fix-issue.sh/validate-pr.sh）用 read -d '' 逐条保真。
        for s in evidence_suites(argv[2:]):
            sys.stdout.write(s + "\0")
        return 0
    if cmd == "final-gate":
        # final-gate —— 确定性测试门命令（ADR-009 唯一取值口；fix-issue.sh
        # / validate-pr.sh read -ra 拆词执行；配置损坏 fail-closed 非零终止）
        print(final_gate_cmd())
        return 0
    if cmd == "docstring-gate":
        # docstring-gate —— docstring 门命令（可选键；空输出=未启用，链脚本跳过）
        if (v := docstring_gate_cmd()) is not None:
            print(v)
        return 0
    if cmd == "parallel-gate":
        # parallel-gate [--failed-tags <path>] —— 并行测试门（ADR-016 段
        # fan-out + 段内并行档；parallel_gate 可选键缺失 → exit 2
        # fail-closed 不产出裁决；--failed-tags 供宿主脚本聚合失败段
        # tag、追加串行段失败后一次裁决，无失败=空文件）
        ftp: str | None = None
        rest = argv[2:]
        j = 0
        while j < len(rest):
            if rest[j] == "--failed-tags":
                if j + 1 >= len(rest):
                    print("parallel-gate: --failed-tags 缺路径参数", file=sys.stderr)
                    return 2
                ftp = rest[j + 1]
                j += 2
            else:
                print(f"parallel-gate: 未知参数 {rest[j]!r}", file=sys.stderr)
                return 2
        return run_parallel_gate(failed_tags_path=ftp)
    if cmd == "local-str":
        # local-str <key> —— 单字符串键输出（feedback-upstream 上游指针等；ADR-009）
        print(_local_str(argv[2]))
        return 0
    if cmd == "metric":
        # metric <node> <t0> <status> —— 节点计时 jsonl 行（shell wrapper 消费）
        print(node_metric_line(argv[2], int(argv[3]), int(time.time()), argv[4]))
        return 0
    if cmd == "local-list":
        # local-list <key> —— 字符串数组键逐行输出（shell for 消费；ADR-009）
        for v in _local_str_list(argv[2]):
            print(v)
        return 0
    if cmd == "jfield":
        # jfield <file> <key> [default] —— shell json_field wrapper 消费
        # （2026-08-28 收口：双引号 -c 内插形态退役，check_inline_python R4 禁形）
        return jfield(argv[2], argv[3], argv[4] if len(argv) > 4 else None)
    if cmd == "dist-manifest":
        # dist-manifest <upstream_repo> <sha> —— sync-from-upstream 分发
        # 清单（2026-08-28 自 heredoc 下沉；无清单=空输出，警告走 stderr）
        for line in dist_manifest_lines(argv[2], argv[3]):
            print(line)
        return 0
    if cmd == "repo-vars":
        # repo-vars —— prompt 仓库参数段（run_node / pr-review / adapt 注入）
        print(repo_vars_text())
        return 0
    print(f"未知子命令: {cmd}", file=sys.stderr)
    return 2
if __name__ == "__main__":
    sys.exit(main(sys.argv))
