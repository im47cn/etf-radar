#!/usr/bin/env python3
"""mutation 冒烟：注入缺陷 → 跑门 → 断言拦截 → 原字节还原。

铁律 5 的机械化：未经本 runner 证明灵敏度的门，不得开启 auto-merge。
"未证明的门不是门。"

两种门：
- guard（篡改类）：guard.py --files 单文件，秒级。
- tests（行为破坏类）：run_tests.sh --no-lock 全量测试门（8 套件 +
  badcase 双通道；--no-lock 跳过 plugin_lock/md_link_check——它们是
  blob 锁与链接门，不消费被注入的行为面），单条分钟级，输出带耗时。
- docstring（文档契约类）：factory-local.json docstring_gate_cmd（可选门，
  缺省不启用；未配置时 docstring 缺陷 SKIP，不构成全绿）——删除公开/内部
  符号 docstring → 门应拦截（对外 API 100% + 内部 ≥80%），单条秒级。

用法:
  python3 .factory/mutations/run.py [--only G-01,B-101] [--defects <path>]

安全策略（重要，先读再跑）:
- 原字节内存备份 + finally 写回；**绝不使用 git checkout / git restore**——
  工作树可能含人工未提交修改，git 还原会抹掉它们。
- target 已被跟踪且工作树相对 index 有未暂存修改 → 该条 SKIP（防与人工
  正在进行的编辑交叠；staged-clean 不 SKIP，见 tracked_and_dirty）。
- 还原后逐文件校验字节一致；不一致 → FATAL、退出码 3、列出残留文件。
- gate 串行执行，注入窗口内无并发读者。

退出码: 0 = 全部按预期；1 = 有 FAIL；2 = 配置错误；3 = 还原失败（需人工介入）；
        4 = 无 FAIL 但有 SKIP（覆盖不完整，不构成 auto-merge 依据）。
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GUARD = REPO_ROOT / ".factory" / "guard.py"


def _final_gate_words(cfg_path: Path | None = None) -> list[str]:
    """tests 门命令（ADR-009 数据化）：factory-local.json final_gate_cmd 拆词。

    词保持配置原样（不绝对化首词、不加 bash 前缀）：run_gate 直执
    （cwd=REPO_ROOT），仓相对脚本（可执行位 + shebang）与 PATH 型命令
    （如 "uv run pytest"）都正常解析——与 shell 侧 fix-issue/validate-pr
    的 "${GATE_ARGS[@]}" 直执同构（R2-M4 + PR #71 Sourcery #1：bash
    前缀会把 PATH 型首词当脚本文件名，必失败）。fail-closed：配置
    缺失/缺键/非字符串/含引号/含换行/空 → RuntimeError（启动即炸，不产生
    无效证据）。类型校验与 factory_lib._local_str 同规（PR #71
    Sourcery #2：str() 静默转换会让数字/列表在 py 侧放行而 shell 侧
    拒绝——两消费方行为必须一致）。
    """
    p = cfg_path or REPO_ROOT / ".factory" / "factory-local.json"
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
        raw_val = cfg["final_gate_cmd"]
        if not isinstance(raw_val, str):
            raise ValueError("final_gate_cmd 须为非空字符串")
        if "\n" in raw_val or "\r" in raw_val:
            raise ValueError("final_gate_cmd 禁含换行（read -r -a 只取首行，shlex 多行拆词，两侧 argv 分歧）")
        raw = raw_val.strip()
        if "'" in raw or '"' in raw:
            raise ValueError("final_gate_cmd 禁含引号（与 bash 侧 read -r -a 拆词一致性，R2-N8）")
        if "\\" in raw:
            raise ValueError("final_gate_cmd 禁含反斜杠（shlex 转义与 read -r 字面语义分叉，ADR-010）")
        words = shlex.split(raw)
        if not words:
            raise ValueError("final_gate_cmd 为空")
    except Exception as exc:
        raise RuntimeError(f"factory-local.json final_gate_cmd 不可用（fail-closed）: {exc}") from exc
    return list(words)


FINAL_GATE = _final_gate_words()


def _docstring_gate_words(cfg_path: Path | None = None) -> list[str] | None:
    """docstring 门命令（可选键）：factory-local.json docstring_gate_cmd 拆词。

    与 _final_gate_words 同构但为**可选**门：仅键缺失 → None（未启用，
    链脚本跳过；mutations 中 docstring 缺陷 SKIP——未启用的门无灵敏度
    可证，不构成全绿）。键存在即校验（非空字符串 + 禁引号/反斜杠/
    换行；键存在但空 = 非法配置，fail-closed RuntimeError，
    禁止静默降级为无门）。阈值（对外 API 100% + 内部 ≥80%）由各仓
    检查器自定，本处只承载命令词。
    """
    p = cfg_path or REPO_ROOT / ".factory" / "factory-local.json"
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
        if "docstring_gate_cmd" not in cfg:
            return None
        raw_val = cfg["docstring_gate_cmd"]
        if not isinstance(raw_val, str):
            raise ValueError("docstring_gate_cmd 须为非空字符串")
        if "\n" in raw_val or "\r" in raw_val:
            raise ValueError("docstring_gate_cmd 禁含换行（read -r -a 只取首行，shlex 多行拆词，两侧 argv 分歧）")
        raw = raw_val.strip()
        if "'" in raw or '"' in raw:
            raise ValueError("docstring_gate_cmd 禁含引号（与 bash 侧 read -r -a 拆词一致性，R2-N8）")
        if "\\" in raw:
            raise ValueError("docstring_gate_cmd 禁含反斜杠（shlex 转义与 read -r 字面语义分叉，ADR-010）")
        words = shlex.split(raw)
        if not words:
            raise ValueError("docstring_gate_cmd 为空")
    except Exception as exc:
        raise RuntimeError(f"factory-local.json docstring_gate_cmd 不可用（fail-closed）: {exc}") from exc
    return list(words)


DOCSTRING_GATE = _docstring_gate_words()

# 门超时预算（tests 门自身无超时参数，此处兜底）。tests 门实测基线
# ~10s；600s ≈ 60 倍余量，超时即无效运行（judge 判 FAIL，不计击杀/放行）。
GUARD_TIMEOUT = 300
TESTS_TIMEOUT = 600

def write_stamp(evidence: str | None = None) -> str | None:
    """全绿出口调用：当前周界 blob 写入 stamp（None = 无法绑定，不写）。

    evidence 指向人工证据留档名；缺省时取 mutations/ 目录最新
    EVIDENCE-*.md（下游 xx-web-tools 反哺：静态默认文件名会过期——
    写戳引用不存在的留档 = stamp 说谎）。无留档如实记「无留档文件」。
    """
    import datetime
    blob = perimeter_blob()
    if not blob:
        return None
    if evidence is None:
        ev_dir = STAMP.parent
        cands = sorted(ev_dir.glob("EVIDENCE-*.md")) if ev_dir.is_dir() else []
        evidence = cands[-1].name if cands else "（无留档文件）"
    STAMP.write_text(json.dumps({
        "perimeter_blob": blob,
        "evidence": evidence,
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return blob

# ── 周界证据指纹绑定（M4，设计 §11.3）────────────────────────────────
# 「改配置 = 改门」：PERIMETER 数据化（factory-local.json）后，周界变更
# 必须仍触发 kill rate 重证——否则门禁灵敏度退化为声明式。机制：全绿
# 退出时把 factory-local.json 的 git blob hash 写入 evidence-stamp.json；
# 下次启动比对，不一致 → 横幅宣告证据过期（本次全绿不构成 auto-merge
# 依据的既有语义不变：人类看横幅决定是否采信）。
# git 环境密闭（PR #71 推送实测事故）：pre-push 钩子环境导出的
# GIT_DIR 等仓库发现变量会劫持 `git -C` 的目标——测试 monkeypatch
# REPO_ROOT 后 git 操作落到真实仓（夹具污染）。剥除之，-C 语义生效。
_GIT_DISCOVERY_VARS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_GRAFT_FILE",
    "GIT_INDEX_VERSION", "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES",
)

_GIT_ENV = {k: v for k, v in os.environ.items()
            if k not in _GIT_DISCOVERY_VARS}

LOCAL_CFG = REPO_ROOT / ".factory" / "factory-local.json"
STAMP = REPO_ROOT / ".factory" / "mutations" / "evidence-stamp.json"


def perimeter_blob() -> str | None:
    """factory-local.json 的 git blob hash（未跟踪/异常 → None = 无法绑定）。"""
    try:
        rel = LOCAL_CFG.relative_to(REPO_ROOT)
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-s", "--", str(rel)],
            capture_output=True, text=True, check=True, env=_GIT_ENV).stdout.split()
        return out[1] if len(out) >= 2 else None
    except Exception:
        return None


def stamp_stale_banner() -> None:
    """启动时宣告上次证据对应的周界指纹与当前不一致（不改变退出码语义）。"""
    try:
        recorded = json.loads(STAMP.read_text(encoding="utf-8"))["perimeter_blob"]
    except Exception:
        return  # 无 stamp（首次运行/旧版本）不宣告
    if recorded != perimeter_blob():
        print("⚠ 周界指纹漂移：evidence-stamp.json 记录的 perimeter_blob 与当前"
              " factory-local.json 不一致——上次证据已过期，本次全绿仅在本次"
              "周界下有效；合并后 evidence-stamp.json 会随本次全绿刷新。")


@dataclass
class Defect:
    id: str
    description: str
    target: str
    find: str
    replace: str
    gate: str
    expect_block: bool


@dataclass
class Outcome:
    defect: Defect
    status: str  # PASS | FAIL | SKIP | FAIL-config
    detail: str = ""


def load_defects(path: Path) -> list[Defect]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    defects = [Defect(**item) for item in raw["defects"]]
    seen = set()
    for d in defects:
        if d.id in seen:
            raise ValueError(f"缺陷 id 重复: {d.id}")
        seen.add(d.id)
        if d.gate not in ("guard", "tests", "docstring"):
            raise ValueError(f"{d.id}: 未知 gate '{d.gate}'")
    return defects


def tracked_and_dirty(rel: str) -> bool:
    """target 被跟踪且工作树相对 index 有未暂存修改 → True（用户正在编辑，须 SKIP）。

    staged-clean（工作树 == index）不 SKIP：内存备份 = staged 内容，注入并
    还原后字节不变、index 未触碰，git 状态无污染。
    """
    ls = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--error-unmatch", rel],
        capture_output=True, env=_GIT_ENV,
    )
    if ls.returncode != 0:
        return False  # 未跟踪（新文件）：内存备份/还原已覆盖安全
    diff = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--quiet", "--", rel],
        capture_output=True, env=_GIT_ENV,
    )
    return diff.returncode != 0


def run_gate(gate: str, target: str) -> int | None:
    """跑门返回退出码；超时返回 None（无效运行，见 judge）。

    超时杀**整个进程组**（start_new_session + killpg）：run_tests.sh 会
    派生 pytest 孙进程，只杀门直子会留下孤儿继续读注入中的 target
    ——finally 还原字节与孤儿运行并发，污染后续缺陷轮（PR #33 审查）。
    """
    if gate == "guard":
        cmd = [sys.executable, str(GUARD), "--files", target]
        timeout = GUARD_TIMEOUT
    else:
        # ADR-009：tests/docstring 门命令自 factory-local.json 拆词后直执
        # ——无 bash 前缀，与 shell 侧 "${GATE_ARGS[@]}" 同构（PR #71
        # Sourcery #1：bash 前缀使 PATH 型命令必失败）；fail-closed 加载
        # 于模块常量段。docstring 门未配置的缺陷已由 main 前置 SKIP，
        # 此处 DOCSTRING_GATE 必非 None。
        cmd = list(FINAL_GATE if gate == "tests" else DOCSTRING_GATE)
        timeout = TESTS_TIMEOUT
    start = time.monotonic()
    # 安全审计落档（PR #33 Sourcery/opengrep dangerous-subprocess-use-audit）：
    # argv 列表形态、无 shell 解释（shell=False 显式）——不存在注入通道。
    # guard 分支参数为闭集（sys.executable + __file__ 推导的模块常量）；
    # tests 分支命令词源自 factory-local.json final_gate_cmd（治理周界
    # .factory/ 内，仅人类 PR 可改；禁引号校验 + shlex 拆词后作为纯 argv
    # 元素传入）；另一外部数据 target 源自 defects.json（同周界），经
    # REPO_ROOT / d.target 与 is_file() 校验后作为单个 argv 数据元素传入，
    # 均不被任何 shell 解析。
    proc = subprocess.Popen(
        cmd, cwd=str(REPO_ROOT), shell=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True)  # 新进程组：pgid == proc.pid
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError) as e:
            # ESRCH：组已自行退出（竞态窗口）。EPERM：macOS XNU 对含
            # 待-reap 僵尸的进程组发信号报 EPERM（同 UID 亦然）——僵尸
            # 无需再杀（SIGKILL 对僵尸本就是 no-op），等 init 收尸即可。
            # 诚实边界（PR #36 审查）：killpg 语义无法区分「仅剩僵尸的
            # EPERM」与「组内有本进程无权发信号的真活进程」；前者成立
            # 的前提是组成员与本进程同 UID——由 argv 闭集（PR #33 安全
            # 审计：无 shell 解释、无 sudo/setuid 通道）保证。若未来
            # gate 获得提权通道，此吞掉点必须复检组内进程状态。
            if isinstance(e, PermissionError):
                print("    killpg=EPERM（僵尸窗口，前提：组成员同 UID，"
                      "见 argv 闭集审计）")
        try:
            proc.communicate(timeout=10)  # 收尸并排干管道
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f"    门超时（>{timeout}s）：已杀进程组，无效运行")
        return None
    elapsed = time.monotonic() - start
    if tail := (out + err).strip().splitlines():
        print(f"    gate 输出末行: {tail[-1][:120]}")
    return proc.returncode


def judge(defect: Defect, rc: int | None) -> tuple[str, str]:
    """门退出码 → (判定, 明细)。
    退出码语义（testing-standards）：rc=0 放行、rc=1 判定失败（击杀证据）；
    其他退出码 / 超时（None）一律**无效运行**——不计击杀也不计放行，
    直接 FAIL。guard 门例外：rc=2 是其 fail-closed 设计（门崩溃=拦截）。
    """
    if rc is None:
        return "FAIL", "门超时（无效运行：不构成击杀/放行证据）"
    if defect.gate in ("tests", "docstring") and rc not in (0, 1):
        return "FAIL", f"无效退出码 rc={rc}（{defect.gate} 门域为 0/1）"
    blocked = rc != 0
    if blocked == defect.expect_block:
        return "PASS", f"blocked={blocked}（rc={rc}）符合预期"
    return "FAIL", f"blocked={blocked}（rc={rc}）不符合预期 expect_block={defect.expect_block}"


def apply_defect(target: Path, defect: Defect) -> str:
    """注入缺陷，返回原文本；find 必须恰好出现一次，否则抛配置错误。"""
    original = target.read_bytes().decode("utf-8")
    count = original.count(defect.find)
    if count != 1:
        raise ValueError(f"锚点出现 {count} 次（要求恰好 1 次）: {defect.find!r}")
    injected = original.replace(defect.find, defect.replace, 1)
    target.write_text(injected, encoding="utf-8")
    return original


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="逗号分隔的缺陷 id 过滤")
    parser.add_argument("--defects", default=str(Path(__file__).parent / "defects.json"))
    args = parser.parse_args()

    defects = load_defects(Path(args.defects))
    stamp_stale_banner()
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        # 下游 xx-web-tools 反哺：未知 id 过滤结果为空仍以 0 退出写戳
        # = 配置错误伪装成全量验证。缺失即拒绝（exit 2，对齐 guard 用法语义）。
        all_ids = {d.id for d in defects}
        if missing := wanted - all_ids:
            print(f"配置错误: --only 含未知缺陷 id: {sorted(missing)}"
                  f"（已知: {sorted(all_ids)}）", file=sys.stderr)
            return 2
        defects = [d for d in defects if d.id in wanted]

    outcomes: list[Outcome] = []
    originals: dict[Path, str] = {}

    for d in defects:
        print(f"[{d.id}] {d.description}（gate={d.gate}）")
        # 下游 xx-web-tools 反哺：d.target 绝对路径会重置 REPO_ROOT 拼接
        # （Path / 语义），`..` 可越仓——--defects 载外部 JSON 时指向仓外
        # 文件注入+写回（进程非正常终止 = 注入残留落仓外）。resolve 后
        # 必须仍在 REPO_ROOT 内。
        target = (REPO_ROOT / d.target).resolve()
        try:
            target.relative_to(REPO_ROOT)
        except ValueError:
            outcomes.append(Outcome(d, "FAIL-config", f"target 越出仓库根: {d.target}"))
            print("    FAIL-config: target 越出仓库根")
            continue
        if not target.is_file():
            outcomes.append(Outcome(d, "FAIL-config", f"target 不存在: {d.target}"))
            print("    FAIL-config: target 不存在")
            continue
        if tracked_and_dirty(d.target):
            outcomes.append(Outcome(d, "SKIP", "target 含人工未提交修改"))
            print("    SKIP: target 含人工未提交修改，避免交叠")
            continue
        if d.gate == "docstring" and DOCSTRING_GATE is None:
            outcomes.append(Outcome(d, "SKIP", "docstring 门未配置（factory-local.json 缺 docstring_gate_cmd，缺省不启用）"))
            print("    SKIP: docstring 门未配置（缺省不启用），缺陷无法验证")
            continue

        original: str | None = None
        try:
            original = apply_defect(target, d)
            originals[target] = original
            rc = run_gate(d.gate, d.target)
            verdict, detail = judge(d, rc)
            outcomes.append(Outcome(d, verdict, detail))
            print(f"    {verdict}: {detail}")
        except ValueError as exc:
            outcomes.append(Outcome(d, "FAIL-config", str(exc)))
            print(f"    FAIL-config: {exc}")
        finally:
            if original is not None:
                target.write_text(original, encoding="utf-8")

    if residual := [
        str(target.relative_to(REPO_ROOT))
        for target, original in originals.items()
        if target.read_text(encoding="utf-8") != original
    ]:
        print(f"\nFATAL: 以下文件还原失败（请人工核对该文件是否已恢复原状）: {residual}",
              file=sys.stderr)
        return 3

    # 汇总（正向按门分组：篡改类 guard / 行为破坏类 tests，负例整体计）
    negative = [o for o in outcomes if not o.defect.expect_block]
    passed_neg = [o for o in negative if o.status == "PASS"]

    print("\n===== mutation 冒烟汇总 =====")
    for o in outcomes:
        print(f"  [{o.defect.id}] {o.status:10s} {o.detail}")
    total_killed = total_positive = 0
    for gate, label in (("guard", "篡改类拦截（guard 门）"),
                        ("tests", "行为破坏类拦截（tests 门）"),
                        ("docstring", "docstring 缺陷拦截（docstring 门）")):
        positive = [o for o in outcomes if o.defect.gate == gate and o.defect.expect_block]
        killed = [o for o in positive if o.status == "PASS"]
        total_killed += len(killed)
        total_positive += len(positive)
        if positive:
            rate = len(killed) / len(positive)
            print(f"  {label}: {len(killed)}/{len(positive)} = {rate:.0%}")
    kill_rate = total_killed / total_positive if total_positive else float("nan")
    print(f"  正向缺陷拦截（kill rate）: {total_killed}/{total_positive} = {kill_rate:.0%}")
    print(f"  负例放行: {len(passed_neg)}/{len(negative)}")

    skipped = [o for o in outcomes if o.status == "SKIP"]
    if any(o.status.startswith("FAIL") for o in outcomes):
        print("  结论: 门灵敏度未达标，禁止开启 auto-merge（铁律 5）")
        return 1
    if skipped:
        ids = ", ".join(o.defect.id for o in skipped)
        print(f"  结论: 覆盖不完整（SKIP: {ids}），本次通过不构成 auto-merge 依据（铁律 5）")
        return 4
    print("  结论: 门灵敏度冒烟通过（auto-merge 的必要非充分条件）")
    if blob := write_stamp():
        print(f"  周界指纹已绑定: {blob[:12]}（evidence-stamp.json）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
