#!/usr/bin/env python3
"""mutation 冒烟：注入缺陷 → 跑门 → 断言拦截 → 原字节还原。

铁律 5 的机械化：未经本 runner 证明灵敏度的门，不得开启 auto-merge。
"未证明的门不是门。"

用法:
  python3 .factory/mutations/run.py [--only G-01,G-03] [--defects <path>]

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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GUARD = REPO_ROOT / ".factory" / "guard.py"
TESTS = REPO_ROOT / "scripts" / "run_tests.sh"


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
        if d.gate not in ("guard", "tests"):
            raise ValueError(f"{d.id}: 未知 gate '{d.gate}'")
    return defects


def tracked_and_dirty(rel: str) -> bool:
    """target 被跟踪且工作树相对 index 有未暂存修改 → True（用户正在编辑，须 SKIP）。

    staged-clean（工作树 == index）不 SKIP：内存备份 = staged 内容，注入并
    还原后字节不变、index 未触碰，git 状态无污染。
    """
    ls = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--error-unmatch", rel],
        capture_output=True,
    )
    if ls.returncode != 0:
        return False  # 未跟踪（新文件）：内存备份/还原已覆盖安全
    diff = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--quiet", "--", rel],
        capture_output=True,
    )
    return diff.returncode != 0


def run_gate(gate: str, target: str) -> int:
    if gate == "guard":
        cmd = [sys.executable, str(GUARD), "--files", target]
    else:
        cmd = ["bash", str(TESTS), "--no-lock"]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    if tail:
        print(f"    gate 输出末行: {tail[-1][:120]}")
    return proc.returncode


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
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        defects = [d for d in defects if d.id in wanted]

    outcomes: list[Outcome] = []
    originals: dict[Path, str] = {}

    for d in defects:
        print(f"[{d.id}] {d.description}")
        target = REPO_ROOT / d.target
        if not target.is_file():
            outcomes.append(Outcome(d, "FAIL-config", f"target 不存在: {d.target}"))
            print("    FAIL-config: target 不存在")
            continue
        if tracked_and_dirty(d.target):
            outcomes.append(Outcome(d, "SKIP", "target 含人工未提交修改"))
            print("    SKIP: target 含人工未提交修改，避免交叠")
            continue

        original: str | None = None
        try:
            original = apply_defect(target, d)
            originals[target] = original
            rc = run_gate(d.gate, d.target)
            blocked = rc != 0
            if blocked == d.expect_block:
                verdict = "PASS"
                detail = f"blocked={blocked}（rc={rc}）符合预期"
            else:
                verdict = "FAIL"
                detail = f"blocked={blocked}（rc={rc}）不符合预期 expect_block={d.expect_block}"
            outcomes.append(Outcome(d, verdict, detail))
            print(f"    {verdict}: {detail}")
        except ValueError as exc:
            outcomes.append(Outcome(d, "FAIL-config", str(exc)))
            print(f"    FAIL-config: {exc}")
        finally:
            if original is not None:
                target.write_text(original, encoding="utf-8")

    # 还原完整性校验：凡注入过的文件，当前字节必须与备份一致
    residual = []
    for target, original in originals.items():
        if target.read_text(encoding="utf-8") != original:
            residual.append(str(target.relative_to(REPO_ROOT)))
    if residual:
        print(f"\nFATAL: 以下文件还原失败（请人工核对该文件是否已恢复原状）: {residual}",
              file=sys.stderr)
        return 3

    # 汇总
    positive = [o for o in outcomes if o.defect.expect_block]
    negative = [o for o in outcomes if not o.defect.expect_block]
    killed = [o for o in positive if o.status == "PASS"]
    passed_neg = [o for o in negative if o.status == "PASS"]
    kill_rate = len(killed) / len(positive) if positive else float("nan")

    print("\n===== mutation 冒烟汇总 =====")
    for o in outcomes:
        print(f"  [{o.defect.id}] {o.status:10s} {o.detail}")
    print(f"  正向缺陷拦截（kill rate）: {len(killed)}/{len(positive)} = {kill_rate:.0%}")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
