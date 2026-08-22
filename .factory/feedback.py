#!/usr/bin/env python3
"""feedback.py — 反哺上游（awesome-rules）的纯函数决策层。

与 state.py 同构：bash（feedback-upstream.sh）编排 git/gh/omp，本模块承载
全部判定逻辑，零 LLM、零副作用（append_ledger 是唯一写操作，由编排器调用）。

候选契约（2026-08-23 升级：逐资产最后触碰者链）：
1. 范围 = PORT_POINT 之后、触碰 .factory/ 的提交。
2. 资产 feedable = 该资产在范围内的【最后触碰者】带 `Upstream-Feedback:
   yes` trailer（或属 BOOTSTRAP_CANDIDATES）——最后意图优先：资产被
   无 trailer 提交特化后整体不反哺（保护上游）；trailer 化演进则
   历史触碰者全部入链（配套件断链自愈，PR #18 实败根治）。判定随
   资产走而非随 commit 走：amend/rebase 换 sha 后，只要资产的
   最后触碰者带 trailer，判定即可重建。
3. 候选 = 触碰任一 feedable 资产的全部提交 − 账本（已反哺 SHA，
   短前缀匹配），cherry-pick 顺序旧→新。

运行：python3 -m pytest .factory/test_feedback.py -o addopts= -q
"""
import json
import pathlib
import re
import subprocess
import sys

# 移植点：2026-08-21 自 awesome-rules 移植工厂（该提交本身是本仓特化，永不反哺）
PORT_POINT = "f6835d15"

# trailer 机制诞生前的可泛化提交（人工判定补录；反哺入账后由账本排除）
BOOTSTRAP_CANDIDATES = {
    "b4c388bd",  # 预建 needs-review 标签 + S1 链占 in-progress 防重复认领
    "c9731cba",  # 标签转移改单请求原子换，失败链终止
    "6997bfc9",  # triage 批次：补齐"写 issue→自动看见"的 S2 缺口
    "246cba05",  # 链改独立 git worktree，根治多驱动方工作区冲突
    "2d61e1bd",  # 三链并发事故修复 D1/D2/D4
    "f550eb73",  # 门禁升级 gauntlet + remote 拓扑动态解析 + WT 目录名契约
    "4657b836",  # 上游 bare 化适配：git 层探测 + 漂移报告走 worktree
}

TRAILER_RE = re.compile(r"^Upstream-Feedback:\s*yes\s*$", re.M | re.I)

# 依赖闭包：.factory 脚本引用的仓库资产（$FACTORY/<path>）；运行时目录产物不算依赖
FACTORY_REF_RE = re.compile(r"\$\{?FACTORY\}?/([\w./+-]+\.(?:py|sh|md))")
RUNTIME_REF_PREFIXES = ("artifacts/", "locks/", "worktrees/", "metrics/",
                        "mutations/")

# 漂移对比时排除的运行时目录（两侧各自的运行痕迹，非工厂资产）
DRIFT_EXCLUDES = [
    "artifacts", "locks", "worktrees", "metrics",
    "__pycache__", ".pytest_cache", "tests/__pycache__",
]



# 资产链判定的运行时排除（带 .factory/ 前缀）：账本是本仓反哺记录，
# 随补录 chore 反复触碰会让 feedable 横跳，且上游不该收本仓账本
ASSET_EXCLUDES = {".factory/feedback-log.jsonl"}

def parse_git_log(text):
    """解析 `git log --format=%H%x00%s%x00%b%x1e` 输出 → [{sha,subject,feedable}]。"""
    commits = []
    for record in text.split("\x1e"):
        parts = [p.strip("\n") for p in record.strip("\n").split("\x00")]
        if len(parts) != 3 or not parts[0]:
            continue
        sha, subject, body = parts
        commits.append({
            "sha": sha,
            "subject": subject,
            "feedable": bool(TRAILER_RE.search(body))
            or any(sha.startswith(b) for b in BOOTSTRAP_CANDIDATES),
        })
    return commits


def feedable_assets(commits):
    """逐资产最后触碰者链：最后触碰者 feedable 的资产集合。

    commits 为 git log 顺序（新→旧）；每资产取最先出现者即最后触碰者
    （线性历史假设，与 cherry-pick 顺序契约一致）。无 files 键的提交
    视为未触碰任何资产。"""
    last_toucher = {}
    for c in commits:
        for f in c.get("files", ()):
            if f in ASSET_EXCLUDES:
                continue
            last_toucher.setdefault(f, c)
    return {f for f, c in last_toucher.items() if c["feedable"]}


def collect_pending(commits, ledger_shas):
    """待反哺候选：触碰任一 feedable 资产 ∧ 不在账本，旧→新。

    判定在资产层（feedable_assets），提交仅作反哺载体——无 trailer
    的历史触碰者随 feedable 资产入链，保证依赖闭包完整。"""
    assets = feedable_assets(commits)
    pending = [c for c in commits
               if set(c.get("files", ())) & assets
               and not any(c["sha"].startswith(s) for s in ledger_shas)]
    return pending[::-1] if pending else []

def extract_factory_refs(text):
    """从 shell 源文本提取 $FACTORY/<资产> 引用；运行时目录产物不算依赖。"""
    return sorted({
        m.group(1) for m in FACTORY_REF_RE.finditer(text)
        if not m.group(1).startswith(RUNTIME_REF_PREFIXES)})


def closure_missing(candidates, upstream_factory_files):
    """依赖闭包：候选触碰的脚本引用的 .factory 资产，必须落在
    上游已有 ∪ 候选触碰 的并集内。返回 {缺失资产: [引用者短 sha]}。

    防 PR #18 实败复演：只反哺了 feedback-upstream.sh，其引用的
    feedback.py / prompts/feedback-adapt.md 未随行——上游拿到即在
    set -e 下死于 cat 不存在的提示词，整条 PR 不可运行。"""
    def _rel(p):
        return p[len(".factory/"):] if p.startswith(".factory/") else p
    projected = {_rel(p) for p in upstream_factory_files}
    for c in candidates:
        projected.update(_rel(p) for p in c.get("files", ()))
    missing = {}
    for c in candidates:
        for ref in extract_factory_refs(c.get("patch", "")):
            if ref not in projected:
                missing.setdefault(ref, []).append(c["sha"][:9])
    return missing

def load_ledger(path):
    """读账本 → 已反哺 SHA 集合（短 sha 前缀匹配用）。文件不存在视为空。"""
    p = pathlib.Path(path)
    if not p.exists():
        return set()
    shas = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # 账本损坏行不阻断收集，保守跳过
        if "sha" in entry:
            shas.add(entry["sha"])
    return shas


def append_ledger(path, sha, subject, upstream_pr, repo):
    """追加一条已反哺记录（jsonl，append-only）。"""
    entry = {
        "sha": sha,
        "subject": subject,
        "repo": repo,
        "upstream_pr": upstream_pr,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def classify_drift(diff_rq_output, upstream_path):
    """解析 `diff -rq <local> <upstream>` 输出 → {upstream_only, local_only, differing}。

    upstream_path 用于判定 "Only in" 行属于哪侧（路径标记，勿硬编码仓名）；
    运行时目录（DRIFT_EXCLUDES）两侧皆排除。
    """
    upstream_only, local_only, differing = [], [], []
    for line in diff_rq_output.splitlines():
        if "Only in" in line:
            if any(x in line for x in DRIFT_EXCLUDES):
                continue
            if line.startswith("Only in %s" % upstream_path):
                upstream_only.append(line)
            else:
                local_only.append(line)
        elif "differ" in line and not any(x in line for x in DRIFT_EXCLUDES):
            differing.append(line)
    return {"upstream_only": upstream_only, "local_only": local_only,
            "differing": differing}


def render_report(pending, drift):
    """dry-run / PR 描述共用的报告文本。"""
    lines = ["—— 待反哺候选（%d 个，cherry-pick 顺序）——" % len(pending)]
    for c in pending:
        lines.append("  %s  %s" % (c["sha"][:9], c["subject"]))
    lines.append("")
    lines.append("—— 上游漂移（仅报告，不自动吸收）——")
    for kind, label in (("upstream_only", "上游独有"), ("differing", "两侧分歧")):
        items = drift.get(kind, [])
        lines.append("  [%s] %d 项" % (label, len(items)))
        for item in items:
            lines.append("    " + item)
    if not drift.get("upstream_only") and not drift.get("differing"):
        lines.append("  （无）")
    return "\n".join(lines)


def status_line(pending_count):
    """factory-state.sh --all 末尾的只读提示行。"""
    if pending_count:
        return "[feedback] 待反哺: %d commits — .factory/feedback-upstream.sh --dry-run 查看" % pending_count
    return "[feedback] 待反哺: 0 — 无需动作"


def _git_log_commits():
    out = subprocess.run(
        ["git", "log", "--format=%H%x00%s%x00%b%x1e",
         "%s..HEAD" % PORT_POINT, "--", ".factory"],
        capture_output=True, text=True, check=True).stdout
    return parse_git_log(out)


def _files_by_sha():
    """sha → 触碰的 .factory 文件集（带 .factory/ 前缀，与 ls-files 一致）。

    记录头 \x1e 标记（\x1e<sha> 开段，--name-only 文件行随后归属本条；
    若分隔符放段尾会把上一条的文件错配给下一条）；线性历史假设与
    cherry-pick 顺序契约一致。"""
    out = subprocess.run(
        ["git", "log", "--format=%x1e%H", "--name-only",
         "%s..HEAD" % PORT_POINT, "--", ".factory"],
        capture_output=True, text=True, check=True).stdout
    files_by_sha = {}
    for record in out.split("\x1e"):
        lines = [ln for ln in record.strip("\n").split("\n") if ln.strip()]
        if not lines:
            continue
        sha, files = lines[0], lines[1:]
        if files:
            files_by_sha.setdefault(sha, set()).update(files)
    return files_by_sha

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    here = pathlib.Path(__file__).parent
    ledger_path = here / "feedback-log.jsonl"
    commits = _git_log_commits()
    fbs = _files_by_sha()
    commits = [dict(c, files=fbs.get(c["sha"], ())) for c in commits]
    ledger = load_ledger(ledger_path)
    pending = collect_pending(commits, ledger)

    if cmd == "pending":
        for c in pending:
            print("%s\t%s" % (c["sha"], c["subject"]))
    elif cmd == "closure":
        # closure <upstream-wt>: 樱桃前 fail-closed——候选引用的资产必须随行可达
        upstream = sys.argv[2]
        out = subprocess.run(
            ["git", "-C", upstream, "ls-files", "--", ".factory"],
            capture_output=True, text=True, check=True).stdout
        ups = [p[len(".factory/"):] for p in out.split()]
        cands = []
        for c in pending:
            patch = subprocess.run(
                ["git", "show", "--format=", c["sha"]],
                capture_output=True, text=True, check=True).stdout
            cands.append(dict(c, patch=patch))
        missing = closure_missing(cands, ups)
        if missing:
            print("依赖闭包缺失（樱桃前 fail-closed）:")
            for ref, shas in sorted(missing.items()):
                print("  %s  ← %s" % (ref, ", ".join(shas)))
            print("处置: 该资产的引入提交补录 BOOTSTRAP_CANDIDATES，"
                  "或提交带 trailer 的资产变更后重跑")
            sys.exit(1)
        print("依赖闭包完备: %d 候选引用的 .factory 资产全部可达" % len(cands))
    elif cmd == "status":
        print(status_line(len(pending)))
    elif cmd == "report":
        upstream = sys.argv[2]
        diff = subprocess.run(
            ["diff", "-rq", str(here), "%s/.factory" % upstream],
            capture_output=True, text=True).stdout
        print(render_report(pending, classify_drift(diff, "%s/.factory" % upstream)))
    elif cmd == "record":
        # record <upstream_pr> <sha>:<subject> [<sha>:<subject> ...]
        upstream_pr = sys.argv[2]
        for arg in sys.argv[3:]:
            sha, subject = arg.split(":", 1)
            append_ledger(ledger_path, sha, subject, upstream_pr,
                          "im47cn/awesome-rules")
        print("账本已更新: %s" % ledger_path)
    else:
        print("用法: feedback.py pending|status|closure <upstream_wt>|"
              "report <upstream_path>|record <pr> <sha>:<subject>...",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
