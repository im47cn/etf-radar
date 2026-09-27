#!/usr/bin/env python3
"""dispatch-liveness — 调度器活性检查（回归第四层组件，2026-08-25）。

多仓形态（同日升级）：检查对象 = hub 注册表 ~/.config/factory/repos.conf
内全部仓库（# 注释与空行忽略），本仓若无注册表则退化为单仓自检——
hub 是多仓唯一调度入口，任一注册仓库的调度死法都是本层的 FAIL 信号。

两种死法都要抓（动机：slug 回归事件暴露的可见性盲区）：
1. 进程在跑但一直失败：cron-dispatch.sh 连击 ≥3 轮 exit 2 会写
   <repo>/.factory/metrics/dispatch-stalled —— 本检查发现它即 FAIL。
2. 进程根本没跑（LaunchAgent 断档，历史实测 13h）：streak 计数文件
   <repo>/.factory/locks/dispatch-fail-streak 正常应随每轮（600s）被
   touch/重写；mtime 超过 FRESH_SECS 未更新 = 该仓库调度未运行，FAIL。
3. GitHub 侧滞留（2026-09-15 issue #165 实证：零改动轮留守 in-progress
   5 天不可见，新失败投进死信筒）：
   a. open issue 挂 factory:in-progress 但 leases/issue:<n>.lock 不存在
      ——链已收官/早亡，无存活租约（锁先于标签获取，标签在而锁不在
      = 滞留，无阈值窗口）；
   b. open issue 挂 factory:rejected：先验回执存在性——只落标无回执
      评论 = 链完整性违规（2026-09-20 #207 实证：落标假阴性早退，
      只落标不发判据 = 不可审计的静默拒绝），不受宽限即时 FAIL；
      有回执且 updatedAt 超过 --stale-days 无人工跟进（拒裁回执评论
      会刷新 updatedAt，故 updatedAt ≥ 拒裁时刻）才计滞留——dispatch
      尾部 rejected-reconcile 对账只在本地日志，本层把静默滞留升为
      回归 FAIL。
   hosting 不可用（无凭据/离线/下游仓未配）→ note 跳过，不误报——
   本地两层（stalled/streak）照常检查。

不 FAIL 的合法状态（每仓独立判定）：
- stalled/streak 均不存在：调度器未启用或从未失败——note 不 FAIL
  （新克隆/禁用调度的开发机不误报）。
- 注册表中的仓库缺 .factory/（未接入工厂的仓库误注册）：note 不 FAIL，
  提示从 repos.conf 移除——registry 是用户侧文件，本检查只读不写。

用法: python3 dispatch_liveness.py [--fresh-secs 93600] [--stale-days 7]
       [--repos PATH]
  --repos 默认 ~/.config/factory/repos.conf（hub 注册表，与
  ~/.config/factory/dispatch-all.sh 同源——单一注册表两处消费）。
  93600s = 26h：日回归节奏下，一轮正常 touch（600s）远远新鲜于阈值。
  --stale-days 默认 7：rejected 滞留人工跟进宽限（日）——rejected 按设计
  等人，宽限内不告警。
退出码: 0=全部活/合法缺省 1=任一仓库死 2=参数/环境错误
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent  # .factory/regression/../..
DEFAULT_REGISTRY = Path.home() / ".config" / "factory" / "repos.conf"


def registry_repos(registry: Path) -> list[Path]:
    """解析 hub 注册表 → 仓库路径清单（# 注释/空行忽略，形态对齐 dispatch-all.sh）。"""
    repos: list[Path] = []
    try:
        lines = registry.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        repos.append(Path(ln).expanduser())
    return repos


def hosting_issues(factory: Path) -> list[dict] | None:
    """hosting.py issue list → 归一化 issue 清单；不可用 → None（降级）。

    只读单次可判定调用（ADR-008 平台抽象，无 gh 直调）。超时/无凭据/
    非 JSON 都归 None：本检查的信条是"合法缺省不误报"，GitHub 侧层
    降级时本地两层照常 FAIL 能力不受影响。
    cwd=repo：hosting.py 的 slug 解析走 `git -C . remote`——必须在
    目标仓自身目录下运行，否则 CWD 仓库劫持 slug（多仓混查同一仓）。
    Codeup 后端工作项面未实装 → 报错归 None，同样降级 note。
    """
    factory = factory.resolve()
    try:
        r = subprocess.run(
            [sys.executable, str(factory / "hosting.py"),
            "issue", "list", "--state", "open", "--limit", "200",
            "--comments"],
            capture_output=True, text=True, timeout=90, cwd=str(factory.parent))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def _gh_updated_age_secs(updated: str | None) -> float | None:
    """gh updatedAt ISO8601 → 距今秒数；不可解析 → None（该检测跳过）。"""
    if not updated:
        return None
    try:
        dt = datetime.datetime.fromisoformat(updated.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds()


def _lease_lock_alive(lock: Path) -> bool:
    """单写者锁文件存活：内容第 5 字段=租期秒（缺省 900），
    mtime+租期 > now = 活；缺失/畸形/过期（SIGKILL 残锁）= 死。"""
    # 回退链对齐权威 _lease_sw_fresh（factory-lease.sh:118）：
    # 第5字段缺 → FACTORY_LEASE_SECS env → 900
    fallback = os.environ.get("FACTORY_LEASE_SECS", "900")
    fallback = int(fallback) if fallback.isdigit() else 900
    try:
        line = lock.read_text(encoding="utf-8").strip().splitlines()[0]
        parts = line.split("|")
        secs = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else fallback
        return lock.stat().st_mtime + secs > time.time()
    except (OSError, IndexError, ValueError):
        return False


def check_stalled_labels(repo: Path, stale_days: int, problems: list[str]) -> str:
    """GitHub 侧滞留检查（第三死法）→ ok/note。FAIL 项追加 problems。

    in-progress 滞留判据（锁先于标签获取、链存活期间持续持有）只在
    单写者形态成立：PG 形态（SUPABASE_DB）租约在 factory_leases 表，
    本地锁文件从不存在——该形态下 in-progress 检测整体降级 note
    （否则每个存活链每天误报滞留，2026-09-16 审查 major）。
    """
    tag = repo.name
    factory = repo / ".factory"
    pg_mode = bool(os.environ.get("SUPABASE_DB"))
    issues = hosting_issues(factory)
    if issues is None:
        print(f"note: [{tag}] hosting 不可用——GitHub 侧滞留检测跳过（本地层已查）")
        return "note"
    n_ok = 0
    for it in issues:
        labels = set(it.get("labels") or [])
        n = it.get("number")
        if "factory:in-progress" in labels:
            if pg_mode:
                # PG 形态租约在库，本地锁文件判据不适用——降级 note
                continue
            # 锁先于标签获取、链存活期间持续持有：标签在而锁不活 = 滞留
            lock = factory / "locks" / "leases" / f"issue:{n}.lock"
            if not _lease_lock_alive(lock):
                problems.append(
                    f"[{tag}] issue #{n} 滞留 factory:in-progress 无存活链租约"
                    "（零改动轮留守或链早亡）——日回归失败会唤醒重派，"
                    "其余滞留请人工裁决关闭")
            else:
                n_ok += 1
        elif "factory:rejected" in labels:
            # 回执存在性先行（#207 实证：落标假阴性早退 → 只落标无
            # 回执，只落标不发判据 = 不可审计的静默拒绝）——链完整性
            # 违规不进宽限时钟，即时 FAIL；回执判据 = 幂等 marker
            # （issue_reject 评论尾埋；标题子串可被人工复述冒充，PR #211
            # Sourcery 评论2），与 factory_lib.rejected_reconcile 同一
            # 判据不得漂移。
            marker = f"factory:receipt:issue-{n}:r"
            if all(
                marker not in str(c.get("body") or "")
                for c in (it.get("comments") or [])
                if isinstance(c, dict)
            ):
                problems.append(
                    f"[{tag}] issue #{n} rejected 无回执评论——链完整性违规"
                    "（#207 同型），需补发回执")
                continue
            age = _gh_updated_age_secs(it.get("updatedAt"))
            if age is not None and age > stale_days * 86400:
                problems.append(
                    f"[{tag}] issue #{n} rejected 滞留 {age/86400:.1f}d 无人工跟进"
                    f"（阈值 {stale_days}d）——dispatch 日志尾部对账有明细，"
                    "请人工裁决处置")
            else:
                n_ok += 1
    if pg_mode:
        print(f"note: [{tag}] PG 租约形态——in-progress 滞留检测降级（租约在库，"
              "本地判据不适用）；rejected 宽限检测照常")
        return "note"
    print(f"ok: [{tag}] GitHub 侧滞留检查：{len(issues)} open issue，{n_ok} 正常/宽限内")
    return "ok"


def check_repo(repo: Path, fresh_secs: int, problems: list[str]) -> str:
    """单仓库活性检查 → 状态行（ok/note）。FAIL 项追加到 problems。"""
    tag = repo.name
    factory = repo / ".factory"
    if not factory.is_dir():
        print(f"note: [{tag}] 无 .factory/（未接入工厂）——建议从 repos.conf 移除")
        return "note"

    stalled = factory / "metrics" / "dispatch-stalled"
    if stalled.exists():
        try:
            detail = stalled.read_text(encoding="utf-8").strip().splitlines()[0]
        except (OSError, IndexError):
            detail = "(标记文件不可读)"
        problems.append(f"[{tag}] dispatch 停摆标记在：{stalled} —— {detail}")

    streak = factory / "locks" / "dispatch-fail-streak"
    if streak.exists():
        age = time.time() - streak.stat().st_mtime
        if age > fresh_secs:
            problems.append(
                f"[{tag}] 调度器疑似断档：streak 文件 {age/3600:.1f}h 未更新"
                f"（阈值 {fresh_secs/3600:.0f}h）——LaunchAgent 未运行？"
                "查 launchctl list | grep factory 与该仓 locks/dispatch.log 尾部")
            return "fail"
        print(f"ok: [{tag}] streak mtime {age/60:.0f}min 前（新鲜）")
        return "ok"
    # 不 FAIL 的理由：调度器未启用/首跑前 streak 尚不存在是合法状态。
    print(f"note: [{tag}] streak 文件不存在（调度器未启用或从未失败）——跳过断档检测")
    return "note"


def main() -> int:
    ap = argparse.ArgumentParser(description="dispatch 调度器活性检查（多仓：hub 注册表）")
    ap.add_argument("--fresh-secs", type=int, default=93600,
                    help="streak 文件新鲜度阈值秒（默认 93600=26h）")
    ap.add_argument("--stale-days", type=int, default=7,
                    help="rejected 滞留人工跟进宽限天数（默认 7）")
    ap.add_argument("--repos", default=str(DEFAULT_REGISTRY),
                    help="hub 注册表路径（默认 ~/.config/factory/repos.conf）")
    args = ap.parse_args()

    registry = Path(args.repos).expanduser()
    repos = registry_repos(registry) if registry.is_file() else []
    if not repos:
        # 无注册表/注册表空：单仓自检（检查器随本仓回归线分发，下游仓
        # 无 hub 时仍可用——退化路径不静默：打印明示只查了谁）
        print(f"note: 注册表不存在或为空（{registry}）——退化为单仓自检")
        repos = [REPO]

    problems: list[str] = []
    for repo in repos:
        check_repo(repo, args.fresh_secs, problems)
        check_stalled_labels(repo, args.stale_days, problems)

    if problems:
        for p in problems:
            print(f"FAIL: {p}", file=sys.stderr)
        return 1
    print(f"ok: {len(repos)} 个仓库全部活性正常（或合法缺省）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
