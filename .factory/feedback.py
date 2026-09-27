#!/usr/bin/env python3
"""feedback.py — 反哺上游的纯函数决策层（上游指针见 factory-local.json）。

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

# 移植点（每仓不同）：首次移植 .factory 的本仓提交——反哺扫描下界，
# 该提交本身是本仓特化永不反哺。数据化到 factory-local.json（ADR-009
# 同构：full 分发文件零本地化，仓特定数据不入代码）；fail-closed：
# 缺键即崩，禁止静默回退默认值——硬编码默认正是 f6835d15 跨仓失效
# 事故根源（下游 git log 128）。
def _load_port_point():
    cfg_path = pathlib.Path(__file__).resolve().parent / "factory-local.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"factory-local.json 不可读: {e}") from e
    pp = cfg.get("port_point")
    if not isinstance(pp, str) or not pp.strip():
        raise RuntimeError(
            "factory-local.json 缺 port_point 键（本仓移植 .factory 的首提"
            "SHA，反哺扫描下界）；fail-closed，禁止默认值")
    return pp


PORT_POINT = _load_port_point()

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


def collect_pending(commits, ledger_shas, ledger_patch_ids=frozenset()):
    """待反哺候选：触碰任一 feedable 资产 ∧ 不在账本，旧→新。

    判定在资产层（feedable_assets），提交仅作反哺载体——无 trailer
    的历史触碰者随 feedable 资产入链，保证依赖闭包完整。
    去重双通道：SHA 前缀（同对象重放）+ patch-id（rebase/amend 后内容
    不变即识别——SHA 去重在本地历史重写后全部失效，已反哺内容会以新
    SHA 重新成为候选、重复反哺；2026-08-22 孪生 SHA 手工补账实证）。
    条目无 patch_id（空 diff 或未计算）时退化为纯 SHA 匹配。"""
    assets = feedable_assets(commits)
    pending = [c for c in commits
               if set(c.get("files", ())) & assets
               and not any(c["sha"].startswith(s) for s in ledger_shas)
               and c.get("patch_id") not in ledger_patch_ids]
    return pending[::-1] if pending else []

def superseded_map(commits, ledger_shas):
    """疑似已随演化反哺：pending 提交的文件集 ⊆ 某更晚已反哺提交的文件集。

    SHA 语义缺口补丁（源仓#66 实证）：反哺走 cherry-pick+适配演化，内容等价
    但 SHA 不一的提交永久 pending，人工识别孪生不可持续。本函数只做确定性
    文件集覆盖判定，产出"疑似"清单供人工确认后 record 补录——不自动入账
    （文件集覆盖是强信号，非内容等价证明）。commits 为 git log 顺序（新→旧），
    "更晚" = 序更靠前；返回 {pending_sha: superseder_sha}。"""
    order = {c["sha"]: i for i, c in enumerate(commits)}
    result = {}
    for c in collect_pending(commits, ledger_shas):
        p_files = set(c.get("files", ()))
        for r in commits[:order[c["sha"]]]:  # 更晚（更新）的提交
            if not any(r["sha"].startswith(s) for s in ledger_shas):
                continue
            if p_files <= set(r.get("files", ())):
                result[c["sha"]] = r["sha"]
                break
    return result

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

def adapt_manifest(pending_text, conflicted_shas):
    """樱桃后候选清单 → manifest 条目（适配节点输入契约，feedback-adapt.md 消费）。

    pending_text：shell 剔除 superseded 后的最终候选（sha\\tsubject 行，旧→新），
    不在此重算——superseded 跳过是 shell 的人工确认决策（亮清单 + record 补录）。
    conflicted_shas：cherry-pick 冲突集。clean 候选同样入清单——审查特化剥离
    必跑，状态只是分流提示。patch 为 fb_dir 相对路径，与 patches/<sha9>.patch
    写入位置对应（adapt-prep 子命令，2026-08-28 自 feedback-upstream.sh
    内嵌 heredoc 下沉，铁律 4：git 子进程编排归 Python）。
    """
    conflicted = set(conflicted_shas)
    items = []
    for line in pending_text.splitlines():
        sha, subject = line.split("\t", 1)
        items.append(
            {
                "sha": sha,
                "subject": subject,
                "status": "conflicted" if sha in conflicted else "clean",
                "patch": f"patches/{sha[:9]}.patch",
            }
        )
    return items

def load_ledger(path):
    """读账本 → 条目 dict 列表（sha 集合由调用方派生）。文件不存在视为空。
    patch_id 持久化（源仓 PR#75 审查）：账本提交对象被 GC 后重算不可得，
    账本是唯一可靠载体；旧条目无此字段 → 调用方退化为重算兜底。"""
    p = pathlib.Path(path)
    if not p.exists():
        return []
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # 账本损坏行不阻断收集，保守跳过
        if "sha" in entry:
            entries.append(entry)
    return entries


def ledger_patch_ids(entries):
    """账本条目 → patch-id 集。持久化值优先（对象被 GC 后重算不可得）；
    旧条目无字段 → 对象仍在时重算兜底（与持久化等价）。"""
    pids = {e["patch_id"] for e in entries if e.get("patch_id")}
    pids |= {p for e in entries if not e.get("patch_id")
             if (p := _patch_id(e["sha"])) is not None}
    return pids


def append_ledger(path, sha, subject, upstream_pr, repo, patch_id=None):
    """追加一条已反哺记录（jsonl，append-only）。patch_id 可为 None
    （空 diff/非资产提交——此类退化纯 SHA 匹配）。"""
    entry = {
        "sha": sha,
        "subject": subject,
        "repo": repo,
        "upstream_pr": upstream_pr,
        "patch_id": patch_id,
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
            if line.startswith(f"Only in {upstream_path}"):
                upstream_only.append(line)
            else:
                local_only.append(line)
        elif "differ" in line and all(x not in line for x in DRIFT_EXCLUDES):
            differing.append(line)
    return {"upstream_only": upstream_only, "local_only": local_only,
            "differing": differing}


def render_report(pending, drift):
    """dry-run / PR 描述共用的报告文本。"""
    lines = ["—— 待反哺候选（%d 个，cherry-pick 顺序）——" % len(pending)]
    lines.extend(f'  {c["sha"][:9]}  {c["subject"]}' for c in pending)
    lines.extend(("", "—— 上游漂移（仅报告，不自动吸收）——"))
    for kind, label in (("upstream_only", "上游独有"), ("differing", "两侧分歧")):
        items = drift.get(kind, [])
        lines.append("  [%s] %d 项" % (label, len(items)))
        lines.extend(f"    {item}" for item in items)
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
        [
            "git",
            "log",
            "--format=%H%x00%s%x00%b%x1e",
            f"{PORT_POINT}..HEAD",
            "--",
            ".factory",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return parse_git_log(out)


def _files_by_sha():
    """sha → 触碰的 .factory 文件集（带 .factory/ 前缀，与 ls-files 一致）。

    记录头 \x1e 标记（\x1e<sha> 开段，--name-only 文件行随后归属本条；
    若分隔符放段尾会把上一条的文件错配给下一条）；线性历史假设与
    cherry-pick 顺序契约一致。"""
    out = subprocess.run(
        [
            "git",
            "log",
            "--format=%x1e%H",
            "--name-only",
            f"{PORT_POINT}..HEAD",
            "--",
            ".factory",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files_by_sha = {}
    for record in out.split("\x1e"):
        lines = [ln for ln in record.strip("\n").split("\n") if ln.strip()]
        if not lines:
            continue
        sha, files = lines[0], lines[1:]
        if files:
            files_by_sha.setdefault(sha, set()).update(files)
    return files_by_sha

def _patch_id(sha):
    """提交 → patch-id（--stable，跨 rebase/amend 内容不变即同 id）。
    空 diff（纯 merge/空提交）返回 None——此类退化纯 SHA 匹配。
    argv 直传不经 shell（源仓 PR#75 审查：注入面收口；--no-ext-diff
    隔离外部 diff 驱动配置，保住 --stable 的跨环境可比性）。"""
    show = subprocess.run(
        ["git", "show", "--format=", "--no-ext-diff", sha],
        capture_output=True, text=True)
    if show.returncode != 0:
        return None
    out = subprocess.run(
        ["git", "patch-id", "--stable"],
        input=show.stdout, capture_output=True, text=True).stdout.strip()
    return out.split()[0] if out else None

def _gather_commits():
    """git log 提交链；files 合并（_files_by_sha 结果挂回提交，供 feedable/pending 判定）。"""
    commits = _git_log_commits()
    fbs = _files_by_sha()
    for c in commits:
        c["files"] = fbs.get(c["sha"], set())
    return commits


def _build_pending(commits, ledger_path):
    """账本加载 → patch-id 附件 → 待反哺候选；返回 (commits, ledger, pending)。"""
    entries = load_ledger(ledger_path)
    ledger = {e["sha"] for e in entries}
    # patch-id 只为触碰 feedable 资产的提交计算（候选判定必要条件，
    # 全历史逐条子进程不可承受）；账本侧优先持久化值（源仓 PR#75 审查）
    assets = feedable_assets(commits)
    commits = [dict(c, patch_id=_patch_id(c["sha"]) if set(c.get("files", ())) & assets else None)
               for c in commits]
    ledger_pids = ledger_patch_ids(entries)
    pending = collect_pending(commits, ledger, ledger_pids)
    return commits, ledger, pending


def _cmd_pending(pending):
    """pending：待反哺候选清单（sha\tsubject，旧→新）。"""
    for c in pending:
        print("%s\t%s" % (c["sha"], c["subject"]))


def _cmd_superseded(commits, ledger, pending):
    # 疑似已随演化反哺（SHA 语义缺口）：sha\tsubject\t<=superseder_sha
    smap = superseded_map(commits, ledger)
    for c in pending:
        if c["sha"] in smap:
            print("%s\t%s\t<=%s" % (c["sha"], c["subject"], smap[c["sha"]]))


def _cmd_closure(upstream, pending):
    # closure <upstream-wt>: 樱桃前 fail-closed——候选引用的资产必须随行可达
    out = subprocess.run(
        ["git", "-C", upstream, "ls-files", "--", ".factory"],
        capture_output=True, text=True, check=True).stdout
    ups = [p[len(".factory/"):] for p in out.split()]
    cands = []
    for c in pending:
        patch = subprocess.run(
            ["git", "show", "--format=", c["sha"]],
            capture_output=True, text=True, check=True).stdout
        files = subprocess.run(
            ["git", "show", "--name-only", "--format=", c["sha"]],
            capture_output=True, text=True, check=True).stdout.split()
        cands.append(dict(c, patch=patch, files=files))
    if missing := closure_missing(cands, ups):
        print("依赖闭包缺失（樱桃前 fail-closed）:")
        for ref, shas in sorted(missing.items()):
            print(f'  {ref}  ← {", ".join(shas)}')
        print("处置: 该资产的引入提交补录 BOOTSTRAP_CANDIDATES，"
              "或提交带 trailer 的资产变更后重跑")
        sys.exit(1)
    print("依赖闭包完备: %d 候选引用的 .factory 资产全部可达" % len(cands))


def _cmd_adapt_prep(fb_dir, pending_text, conflicted_shas):
    # adapt-prep <fb_dir> <pending> <conflicted_sha>... —— 写适配节点输入：
    # patches/<sha9>.patch（git show --format=fuller 全文）+ manifest.json
    fb_dir = pathlib.Path(fb_dir)
    items = adapt_manifest(pending_text, conflicted_shas)
    for it in items:
        (fb_dir / it["patch"]).write_text(subprocess.run(
            ["git", "show", "--format=fuller", it["sha"]],
            capture_output=True, text=True, check=True).stdout,
            encoding="utf-8")
    (fb_dir / "manifest.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print("适配输入就绪: %s（%d 候选，冲突 %d）" % (
        fb_dir / "manifest.json", len(items),
        sum(i["status"] == "conflicted" for i in items)))


def _cmd_report(upstream, pending, here):
    """report：漂移对比（diff -rq）+ 待反哺候选 → 报告文本。"""
    diff = subprocess.run(
        ["diff", "-rq", str(here), f"{upstream}/.factory"],
        capture_output=True,
        text=True,
    ).stdout
    print(render_report(pending, classify_drift(diff, f"{upstream}/.factory")))


def _cmd_record(upstream_pr, args, ledger_path):
    # ADR-009：账本的上游 repo 记 factory-local.json（fail-closed，禁止硬编码）
    cfg = json.loads(pathlib.Path(__file__).parent.joinpath(
        "factory-local.json").read_text(encoding="utf-8"))
    upstream_repo = str(cfg["upstream_repo"])
    for arg in args:
        sha, subject = arg.split(":", 1)
        append_ledger(ledger_path, sha, subject, upstream_pr,
                      upstream_repo, patch_id=_patch_id(sha))
    print(f"账本已更新: {ledger_path}")


def _usage_exit():
    """未知/缺失子命令 → 用法说明到 stderr，退出码 2。"""
    print("用法: feedback.py pending|superseded|status|closure <upstream_wt>|"
          "report <upstream_path>|adapt-prep <fb_dir> <pending> <conflicted>...|"
          "record <pr> <sha>:<subject>...",
          file=sys.stderr)
    sys.exit(2)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    here = pathlib.Path(__file__).parent
    ledger_path = here / "feedback-log.jsonl"
    commits = _gather_commits()
    commits, ledger, pending = _build_pending(commits, ledger_path)

    if cmd == "pending":
        _cmd_pending(pending)
    elif cmd == "superseded":
        _cmd_superseded(commits, ledger, pending)
    elif cmd == "closure":
        _cmd_closure(sys.argv[2], pending)
    elif cmd == "adapt-prep":
        _cmd_adapt_prep(sys.argv[2], sys.argv[3], sys.argv[4:])
    elif cmd == "status":
        print(status_line(len(pending)))
    elif cmd == "report":
        _cmd_report(sys.argv[2], pending, here)
    elif cmd == "record":
        _cmd_record(sys.argv[2], sys.argv[3:], ledger_path)
    else:
        _usage_exit()


if __name__ == "__main__":
    main()
