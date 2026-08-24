#!/usr/bin/env bash
# dispatch.sh — S2 派发器（零 LLM，设计 A3/§7 骨架）。
#
# 职责边界（唯一命令式写标签的地方）：
#   - claim：accepted → in-progress（consume 队列；GitHub 无原子换标签，
#     单实例部署是互斥的真实保证，sync 收敛漂移）
#   - 重派：needs-fix（且非 needs-human）→ 关联 issue re-claim。
#     计数契约：重派必须 remove factory:needs-fix——label 事件只在添加时
#     触发，标签滞留则 state.py 的轮次计数冻结（test_state.py 有边界测试）
#   - merge：仅当 reviewDecision=APPROVED 且 A5 门开
#     （FACTORY_AUTO_MERGE=1 且 .factory/metrics/auto-merge-unlocked 存在；
#     mutations kill-rate ≥80% 前不得开启——设计 A5"未证明的门不是门"）
#   - 其余一切标签由 factory-state.sh sync 从事实推导（声明式）
#
# 固定优先级：PR 结果处理 > fix-issue 派发（§7：validate-pr > fix-issue > triage；
# triage 在本形态内联于 fix-issue.sh，无独立批）
# 链失败（fix-issue.sh 非零退出）→ 其 trap 清 triaging/accepted/in-progress，
# issue 回零标签态，人工重投或重开 issue（设计：失败清理，可观测非门）
#
# 用法: dispatch.sh [--dry-run] [--watch] [--interval SEC]
#   默认单轮；--watch 常驻（默认 1800s，对齐设计 cron 30min）
#   DRY 环境变量与 --dry-run 等价（2026-08-21 事故教训：两者都认）
set -u
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "不在 git 仓库" >&2; exit 2; }
FACTORY="$REPO/.factory"
REPO_SLUG="${GH_REPO:-$(
  # 双 remote 布局：origin pushurl 可能多条（codeup 镜像 + github），
  # 逐条扫含 github.com 者（github remote 名优先）；443 端口形态兼容
  { git -C "$REPO" remote get-url --all --push github 2>/dev/null
    git -C "$REPO" remote get-url --all --push origin 2>/dev/null
  } | grep -m1 'github\.com' | sed -E 's#^.*github\.com(:[0-9]+)?[/:]##; s#\.git$##'
)}"
[ -n "$REPO_SLUG" ] || { echo "无法确定 GitHub 仓库 slug" >&2; exit 2; }

DRY="${DRY:-0}"; WATCH=0; INTERVAL="${INTERVAL:-1800}"
MAX_PARALLEL="${MAX_PARALLEL:-4}"  # worktree 隔离(246cba05)+D1/D4 修复(e2e 2026-08-22 issue#64 全绿)后恢复并行
MERGE_METHOD="${FACTORY_MERGE_METHOD:-merge}"
AUTO_MERGE=0
[ "${FACTORY_AUTO_MERGE:-0}" = 1 ] && [ -f "$FACTORY/metrics/auto-merge-unlocked" ] && AUTO_MERGE=1

for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --watch) WATCH=1 ;;
    --interval) : ;;  # 值由下一参数给出，循环里跳过
  esac
done
# --interval N（取参数值）
prev=""
for a in "$@"; do
  [ "$prev" = "--interval" ] && INTERVAL="$a"
  prev="$a"
done

gh >/dev/null 2>&1 || { echo "需要 gh CLI" >&2; exit 2; }

# --- 双实例硬锁：mkdir 原子性 + PID 活性检测（macOS 无 flock(1)） ---
# GitHub 换标签非原子，claim 互斥完全依赖单 dispatcher；此锁把"文档假设"
# 变成进程级事实。cron 包装器（cron-dispatch.sh）与本脚本共用此锁。
# 跨 worktree 全局（39b6b8e 思想）：链在独立 worktree/派发树跑后各树
# locks/ 互不可见，锁随树走会绕开互斥。git-common-dir 在 worktree 中
# 指向主 .git，据此回到主树 .factory。
MAIN_FACTORY="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null \
  | sed 's#/\.git$##')/.factory"
LOCKDIR="${MAIN_FACTORY:-$FACTORY}/locks/dispatcher"
acquire_lock() {
  # 父目录预建（同 fix-issue.sh：单级 mkdir 原子声明，父缺 ENOENT 会
  # 被误读为"另一 dispatcher 运行中"）
  mkdir -p "${LOCKDIR%/*}" 2>/dev/null || true
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$LOCKDIR/pid"
    trap 'rm -rf "$LOCKDIR"' EXIT
    return 0
  fi
  local pid; pid="$(cat "$LOCKDIR/pid" 2>/dev/null || true)"
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    echo "锁持有者 pid=${pid} 已死，接管陈锁" >&2
    rm -rf "$LOCKDIR"
    mkdir "$LOCKDIR" && echo $$ > "$LOCKDIR/pid" \
      && trap 'rm -rf "$LOCKDIR"' EXIT && return 0
  fi
  echo "另一 dispatcher 运行中（pid=${pid}），退出" >&2; return 1
}
acquire_lock || exit 0

say() { [ "$DRY" = 1 ] && echo "  [dry-run] $*" || echo "  $*"; }

claim() {  # <issue-number>  消费 accepted → in-progress（幂等重试 ×2）
  local N="$1" rc=0
  for _retry in 1 2; do
    if [ "$DRY" = 1 ]; then say "claim issue #$N: accepted → in-progress"; return 0; fi
    gh issue edit "$N" --repo "$REPO_SLUG" \
      --remove-label factory:accepted --add-label factory:in-progress >/dev/null 2>&1 && rc=0 || rc=$?
    [ "$rc" = 0 ] && return 0
  done
  echo "  claim #$N 失败（并发或权限），跳过" >&2; return 1
}

run_chain() {  # <issue-number>  占并发槽运行链
  if [ "$DRY" = 1 ]; then say "run: bash .factory/fix-issue.sh $1"; return 0; fi
  # FACTORY_DISPATCHED=1: 链知道自己已被 dispatcher 锁护，S1 手动互斥锁免获取(防自锁)
  FACTORY_DISPATCHED=1 bash "$FACTORY/fix-issue.sh" "$1" >> "$FACTORY/artifacts/issue-$1/dispatch.log" 2>&1 &
  while [ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$MAX_PARALLEL" ]; do sleep 5; done
}

pr_link_issue() {  # <pr-number> → issue 号
  gh pr view "$1" --repo "$REPO_SLUG" --json body \
    | python3 "$FACTORY/state.py" link /dev/stdin
}

sort_by_priority() {  # accepted issue 号按 priority:* 降序（critical>high>medium>low）
  python3 -c '
import json, sys
rank = {"priority:critical": 0, "priority:high": 1, "priority:medium": 2, "priority:low": 3}
rows = [(min((rank.get(l["name"], 9) for l in i["labels"]), default=9), i["number"])
        for i in json.load(sys.stdin)]
for _, n in sorted(rows): print(n)'
}

dispatch_once() {
  echo "=== dispatch @ $(date '+%H:%M:%S') ==="
  say "sync: factory-state.sh sync --all"
  [ "$DRY" = 0 ] && bash "$FACTORY/factory-state.sh" sync --all

  echo "-- PR 结果处理（优先） --"
  # approved：sync 已打好标签；此处只做 A5 门内的 merge 动作
  # 注意：列表用命令替换读入、主 shell for 迭代——管道 while 子 shell
  # 里的后台链不进主 shell job 表，wait 等不到（孤儿链事故 2026-08-21）
  APPROVED="$(gh pr list --repo "$REPO_SLUG" --state open --label factory:approved \
    --json number,mergeable,reviewDecision --limit 50 \
    | python3 -c '
import json, sys
for pr in json.load(sys.stdin):
    if pr["reviewDecision"] == "APPROVED":
        print(pr["number"], pr["mergeable"])')"
  for entry in $APPROVED; do
    set -- $entry; P="$1"; MERGEABLE="$2"
    if [ "$AUTO_MERGE" = 1 ] && [ "$MERGEABLE" = "MERGEABLE" ]; then
      say "merge PR #$P (--$MERGE_METHOD)"
      [ "$DRY" = 0 ] && gh pr merge "$P" --repo "$REPO_SLUG" "--$MERGE_METHOD" --admin >/dev/null \
        && echo "  PR #$P 已合并；issue 由 GitHub 自动关闭"
    else
      echo "  PR #$P approved 但 A5 门未开（FACTORY_AUTO_MERGE + metrics/auto-merge-unlocked）→ 人工合并"
    fi
  done

  echo "-- needs-fix 重派（计数契约：claim 时移除 needs-fix） --"
  NEEDS_FIX="$(gh pr list --repo "$REPO_SLUG" --state open --label factory:needs-fix \
    --json number --limit 50 \
    | python3 -c '
import json, sys
for pr in json.load(sys.stdin): print(pr["number"])')"
  for P in $NEEDS_FIX; do
    N="$(pr_link_issue "$P")"
    [ -z "$N" ] && { echo "  PR #$P 无关联 issue（body 缺 Closes #N），跳过" >&2; continue; }
    # issue 已在跑（in-progress）则不重复派
    if gh issue view "$N" --repo "$REPO_SLUG" --json labels -q '.labels[].name' 2>/dev/null \
       | grep -q '^factory:in-progress$'; then
      echo "  issue #$N 已 in-progress，跳过"; continue
    fi
    say "PR #$P → issue #$N 重派（remove needs-fix 保计数活性）"
    [ "$DRY" = 0 ] && gh pr edit "$P" --repo "$REPO_SLUG" --remove-label factory:needs-fix >/dev/null
    if claim "$N"; then run_chain "$N"; fi
  done

  echo "-- accepted 队列（priority 排序，并发 ≤${MAX_PARALLEL}） --"
  QUEUE="$(gh issue list --repo "$REPO_SLUG" --state open --label factory:accepted \
    --json number,labels --limit 100 | sort_by_priority)"
  for N in $QUEUE; do
    # D4(2026-08-21 实证双派): gh label 过滤是"含有"而非"仅有"，
    # accepted+in-progress 双标签条目仍在队列，必须显式跳过在跑的
    if gh issue view "$N" --repo "$REPO_SLUG" --json labels -q '.labels[].name' 2>/dev/null \
       | grep -q '^factory:in-progress$'; then
      echo "  issue #$N 已 in-progress，跳过"; continue
    fi
    if claim "$N"; then say "issue #$N → 链"; run_chain "$N"; fi
  done

  if [ "$DRY" = 0 ]; then
    wait; echo "本轮链全部结束，收尾 sync"
    bash "$FACTORY/factory-state.sh" sync --all
    # worktree 驻留分支归位（链后 HEAD 悬在 issue 分支上；归位让
    # git worktree list 状态可预测，专属分支=专属 worktree 约定）
    git -C "${REPO}" checkout -q factory/base 2>/dev/null || true
  fi
}

if [ "$WATCH" = 1 ]; then
  while true; do dispatch_once; sleep "$INTERVAL"; done
else
  dispatch_once
  [ "$DRY" = 0 ] && echo "提示: --watch 常驻（或 cron */30 调用单轮）"
fi
