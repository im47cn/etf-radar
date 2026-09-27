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

# 周界数据外置（M4，设计 §11.3）：PERIMETER 从 factory-local.json 载入——
# 本文件零本地化、跨仓 full 分发；每仓的周界是数据（skip 分发）。
# fail-closed：配置缺失/损坏/缺键 → 异常 → exit 2（门坏等同拦截）。
# MISSION.md 仍是唯一真相源：self_check 每次运行核对一致性（下方）。
def _load_perimeter() -> tuple[str, ...]:
    import json
    cfg_path = Path(__file__).resolve().parent / "factory-local.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        perimeter = cfg["perimeter"]
        if not isinstance(perimeter, list) or not perimeter \
                or not all(isinstance(p, str) and p.strip() for p in perimeter):
            raise ValueError("perimeter 须为非空字符串列表")
        return tuple(perimeter)
    except Exception as exc:
        raise RuntimeError(f"factory-local.json 不可用（fail-closed）: {exc}") from exc
PERIMETER: tuple[str, ...] = ()
_LOAD_ERROR: RuntimeError | None = None
try:
    PERIMETER = _load_perimeter()
except RuntimeError as exc:
    # 库导入不崩（测试可用）；CLI 路径在 main 首行 raise → exit 2
    _LOAD_ERROR = exc

def self_check() -> None:
    """核对 PERIMETER 副本与 MISSION.md 周界清单一致，且每条路径真实存在。

    防两类静默失效：人工只改一边造成锁漂移；周界指向已移动/删除的路径
    （如目录重构后清单未跟随，实际保护对象悄然消失）。两者均为 exit 2。
    存在性豁免 gitignored 路径：fresh clone 检不出它们且无主树可回退，
    缺失是正常态而非漂移；非忽略路径缺失仍视为漂移拦截。
    """
    text = (REPO_ROOT / "MISSION.md").read_text(encoding="utf-8")
    m = re.search(r"## 周界（PERIMETER）(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        raise RuntimeError("MISSION.md 缺少「## 周界（PERIMETER）」一节")
    mission_paths = {p for p in re.findall(r"`([^`\n]+)`", m[1]) if p.strip()}
    guard_paths = set(PERIMETER)
    if mission_paths != guard_paths:
        raise RuntimeError(
            f"PERIMETER 与 MISSION.md 周界清单不一致（MISSION 独有: {sorted(mission_paths - guard_paths)}；guard 独有: {sorted(guard_paths - mission_paths)}）"
        )
    # 存在性三态（fresh-clone 容错 + worktree 兼容）：
    #   gitignored（.crush/、.vscode/ 等本机配置）→ 不要求存在——fresh
    #   clone 检不出且无主树可回退，缺失是正常态非漂移；
    #   其余 → 当前树 ∪ 主工作树（未跟踪非忽略目录可能只在主树）；
    #   两边皆缺且非 ignored → M-02 的「从未存在」，仍拦。
    import subprocess
    rp = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True,
    )
    if rp.returncode != 0:
        # 主树回退依赖 git 元数据：失败即放弃回退（fail-safe 偏严——
        # 多拦误报不放过漂移），与下方 check-ignore fail-closed 立场一致。
        # None 而非 ""：Path("")/p 会相对当前工作目录解析，CWD 同名周界
        # 路径可令 exists() 误真放行——None 语义彻底禁掉主树回退分支
        main_root = None
    else:
        main_root = rp.stdout.strip().removesuffix("/.git")
    if absent := [
        p
        for p in sorted(guard_paths)
        if not (REPO_ROOT / p).exists() and (
            main_root is None or not (Path(main_root) / p).exists()
        )
    ]:
        # check-ignore 批量豁免（rc 0=有命中 1=全否）；git 失败 fail-closed
        ci = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "--stdin"],
            input="\n".join(absent), capture_output=True, text=True,
        )
        if ci.returncode not in (0, 1):
            raise RuntimeError(f"git check-ignore 异常（fail-closed）: rc={ci.returncode}")
        ignored = {line.rstrip("/") for line in ci.stdout.splitlines() if line.strip()}
        if missing := [p for p in absent if p.rstrip("/") not in ignored]:
            raise RuntimeError(f"周界路径不存在（疑似漂移）: {missing}")


def normalize(path: str) -> str:
    """规范化 diff 路径：去 ./ 前缀、反斜杠转正斜杠。

    只剥字面 "./" 两字符前缀——lstrip("./") 会连剥所有前导点/斜杠，
    把 .factory/forge 变成 factory/forge，点前缀周界（.factory/、
    .github/、.gitignore）整体失效（2026-08-25 ADR-007 移植实测；
    上游 mutations 锚点无点文件故未暴露）。"""
    p = path.strip().replace("\\", "/")
    return p.removeprefix("./")


def violates(path: str) -> str | None:
    """命中周界则返回命中的前缀，否则 None。目录以路径前缀匹配。"""
    if p := normalize(path):
        return next(
            (entry for entry in PERIMETER if p == entry or p.startswith(entry)),
            None,
        )
    else:
        return None


def diff_names(base: str, head: str) -> list[str]:
    """merge-base 三点 diff 的变更文件列表。git 失败 → 抛异常 → exit 2。"""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff 失败: rc={proc.returncode}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    if _LOAD_ERROR is not None:
        raise _LOAD_ERROR  # fail-closed：配置坏 → __main__ except → exit 2
    self_check()
    paths: list[str]
    if len(argv) >= 3 and argv[1] == "--base":
        base = argv[2]
        rest = argv[3:]
        head = rest[1] if rest and rest[0] == "--head" and len(rest) >= 2 else "HEAD"
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
        if entry := violates(path):
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
