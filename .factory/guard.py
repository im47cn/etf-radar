#!/usr/bin/env python3
"""治理锁（guard）：周界 hard-fail 检查。

铁律 3 的机械化：任何触碰 PERIMETER 的变更集直接判死，无论内容多合理。
周界变更只能走人类 PR（分支保护 + CODEOWNERS）。

设计约束（第一性原理见 docs/design/factory-harness-design.md §6）：
- 零第三方依赖：标准库即可运行，随 git 裸仓库可用。
- 蠢而可审计：纯字符串前缀匹配，无启发式、无 LLM。
- fail-closed：任何内部异常都返回非零（门坏了等同于拦截）。
- 本文件自身位于 .factory/ 周界内：篡改门 = 门崩溃或拦下，均非放行。

用法:
  PR 模式:   python3 .factory/guard.py --base origin/main [--head HEAD]
  列表模式:  python3 .factory/guard.py --files <path> [<path> ...]
  stdin 模式: git diff --name-only <base>...<head> | python3 .factory/guard.py

退出码: 0 = 干净；1 = 触碰周界；2 = 用法或内部错误。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 与 MISSION.md「周界（PERIMETER）」一节保持同步：MISSION.md 是唯一真相源，
# 此处是机械化副本；每次运行由 self_check 自动核对一致性（漂移即 fail-closed）。
PERIMETER = (
    # 治理
    "MISSION.md",
    "CLAUDE.md",
    "AGENTS.md",
    "docs/CONVENTIONS.md",
    "docs/design/",
    # 质检线
    ".factory/",
    "scripts/",
    ".githooks/",
    ".github/",
    # 数据面
    "data/",
    "config/",
    "supabase/",
    # 依赖与发布面
    "backend/pyproject.toml",
    "backend/uv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
    "package.json",
    "package-lock.json",
    ".gitignore",
    ".mcp.json",
    ".claude/",
)

def self_check() -> None:
    """核对 PERIMETER 副本与 MISSION.md 周界清单一致，且每条路径真实存在。

    防两类静默失效：人工只改一边造成锁漂移；周界指向已移动/删除的路径
    （如目录重构后清单未跟随，实际保护对象悄然消失）。两者均为 exit 2。
    """
    text = (REPO_ROOT / "MISSION.md").read_text(encoding="utf-8")
    m = re.search(r"## 周界（PERIMETER）(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        raise RuntimeError("MISSION.md 缺少「## 周界（PERIMETER）」一节")
    mission_paths = {p for p in re.findall(r"`([^`\n]+)`", m.group(1)) if p.strip()}
    guard_paths = set(PERIMETER)
    if mission_paths != guard_paths:
        raise RuntimeError(
            "PERIMETER 与 MISSION.md 周界清单不一致（MISSION 独有: %s；guard 独有: %s）"
            % (sorted(mission_paths - guard_paths), sorted(guard_paths - mission_paths))
        )
    # worktree 兼容：未跟踪配置目录（.crush/ 等）可能未检出本 worktree，
    # 但存在于主工作树——存在性 = 当前树 ∪ 主树（M-02 的"从未存在"仍拦）
    import subprocess
    main_root = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True,
    ).stdout.strip().removesuffix("/.git")
    missing = [
        p for p in sorted(guard_paths)
        if not (REPO_ROOT / p).exists() and not (Path(main_root) / p).exists()
    ]
    if missing:
        raise RuntimeError(f"周界路径不存在（疑似漂移）: {missing}")


def normalize(path: str) -> str:
    """规范化 diff 路径：去 ./ 前缀、反斜杠转正斜杠、丢弃删除标记。"""
    p = path.strip().lstrip("./")
    return p.replace("\\", "/")


def violates(path: str) -> str | None:
    """命中周界则返回命中的前缀，否则 None。目录以路径前缀匹配。"""
    p = normalize(path)
    if not p:
        return None
    for entry in PERIMETER:
        if p == entry or p.startswith(entry):
            return entry
    return None


def diff_names(base: str, head: str) -> list[str]:
    """merge-base 三点 diff 的变更文件列表。git 失败 → 抛异常 → exit 2。"""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff 失败: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    self_check()
    paths: list[str]
    if len(argv) >= 3 and argv[1] == "--base":
        base = argv[2]
        head = "HEAD"
        rest = argv[3:]
        if rest and rest[0] == "--head" and len(rest) >= 2:
            head = rest[1]
        paths = diff_names(base, head)
    elif len(argv) >= 3 and argv[1] == "--files":
        paths = argv[2:]
    elif len(argv) == 1 and not sys.stdin.isatty():
        paths = [line for line in sys.stdin.read().splitlines() if line.strip()]
    else:
        print(__doc__, file=sys.stderr)
        return 2

    hits: list[tuple[str, str]] = []
    for path in paths:
        entry = violates(path)
        if entry:
            hits.append((path, entry))

    if hits:
        print("GUARD: 变更触碰周界，hard-fail（周界变更请走人类 PR）：", file=sys.stderr)
        for path, entry in hits:
            print(f"  - {path}  (命中: {entry})", file=sys.stderr)
        print("依据: MISSION.md 周界清单 + 铁律 3（治理不可自改）", file=sys.stderr)
        return 1

    print(f"GUARD: 通过（{len(paths)} 个变更文件，0 命中周界）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:  # fail-closed：门坏了等同于拦截
        print(f"GUARD: 内部错误（fail-closed，视为拦截）: {exc}", file=sys.stderr)
        sys.exit(2)
