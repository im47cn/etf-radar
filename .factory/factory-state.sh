#!/usr/bin/env bash
# factory-state.sh — 标签同步器：GitHub 事实 → state.py plan → 应用。
#
# 第一性原理（防"转移实现一半"）：issue/PR 的可观测状态不由链各步骤顺手
# 写标签维护，而是本脚本从仓库可见事实（PR 存在性、reviewDecision、
# label-add 事件计数、链标记评论）整体推导并幂等收敛。链内的即时打标
# 保留作新鲜度优化；本脚本兜底完整性——漏写转移在这里不存在，因为没有
# 转移代码，只有状态函数。锁（triaging/in-progress）除外，见 state.py。
#
# 用法: factory-state.sh sync [N|--all] [--plan]
#   sync 2        同步单个 issue（含其关联 PR 两侧标签）
#   sync --all    同步所有带 factory:* 标签的 issue
#   --plan        只打印计划操作，不执行
set -u
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "不在 git 仓库" >&2; exit 2; }
FACTORY="$REPO/.factory"
REPO_SLUG="${GH_REPO:-$(git -C "$REPO" remote get-url origin 2>/dev/null \
  | sed -E 's#.*github\.com[:/]##; s#\.git$##')}"
[ -n "$REPO_SLUG" ] || { echo "无法确定 GitHub 仓库 slug（GH_REPO 或 github remote）" >&2; exit 2; }

TARGET=""; PLAN=0
for a in "$@"; do
  case "$a" in
    --all) TARGET="--all" ;;
    --plan) PLAN=1 ;;
    *) TARGET="$a" ;;
  esac
done
[ -n "$TARGET" ] || { echo "用法: $0 sync <N|--all> [--plan]" >&2; exit 2; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

find_pr_for_issue() {  # <issue-number> → PR number（空=无）
  gh pr list --repo "$REPO_SLUG" --state open --limit 100 \
    --json number,body,reviewDecision,labels,state \
    | python3 -c '
import json, re, sys
n = int(sys.argv[1])
for pr in json.load(sys.stdin):
    if re.search(r"[Cc]loses #%d\b" % n, pr.get("body") or ""):
        print(pr["number"]); break
' "$1"
}

sync_one() {  # <issue-number>
  local N="$1" P="" plan=""
  gh issue view "$N" --repo "$REPO_SLUG" \
    --json number,state,labels,comments > "$TMP/issue.json" 2>/dev/null \
    || { echo "  issue #$N 不可读，跳过" >&2; return 0; }
  P="$(find_pr_for_issue "$N")"
  if [ -n "$P" ]; then
    gh pr view "$P" --repo "$REPO_SLUG" \
      --json number,state,reviewDecision,labels > "$TMP/pr.json"
    gh api "repos/${REPO_SLUG}/issues/${P}/events" --paginate > "$TMP/events.json"
    plan="$(python3 "$FACTORY/state.py" plan \
      --issue "$TMP/issue.json" --pr "$TMP/pr.json" --events "$TMP/events.json")"
  else
    plan="$(python3 "$FACTORY/state.py" plan --issue "$TMP/issue.json")"
  fi

  local phase; phase="$(printf '%s' "$plan" | python3 -c 'import json,sys; print(json.load(sys.stdin)["phase"])')"
  echo "issue #$N phase=${phase}"

  if [ "$PLAN" = 1 ]; then
    printf '%s' "$plan" | python3 -c 'import json,sys
for o in json.load(sys.stdin)["ops"]:
    print("  [plan] %s %s %s" % (o["target"], o["op"], o["label"]))'
    return 0
  fi

  printf '%s' "$plan" | python3 -c 'import json,sys
for o in json.load(sys.stdin)["ops"]:
    print("%s\t%s\t%s" % (o["target"], o["op"], o["label"]))' \
    | while IFS=$'\t' read -r tgt op label; do
        if [ "$tgt" = issue ]; then
          gh issue edit "$N" --repo "$REPO_SLUG" "--${op}-label" "$label" >/dev/null \
            && echo "  [label] issue $op $label" \
            || echo "  [label] issue $op $label 失败（仅告警）" >&2
        else
          gh pr edit "$P" --repo "$REPO_SLUG" "--${op}-label" "$label" >/dev/null \
            && echo "  [label] pr $op $label" \
            || echo "  [label] pr $op $label 失败（仅告警）" >&2
        fi
      done
}

if [ "$TARGET" = "--all" ]; then
  gh issue list --repo "$REPO_SLUG" --state all --limit 200 --json number,labels \
    | python3 -c '
import json, sys
for i in json.load(sys.stdin):
    if any(l["name"].startswith("factory:") for l in i["labels"]):
        print(i["number"])' \
    | while read -r N; do sync_one "$N"; done
else
  sync_one "$TARGET"
fi
