#!/usr/bin/env bash
# factory-state.sh — 标签同步器：托管平台事实（hosting.py，ADR-008）→ state.py plan → 应用。
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
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  # 诊断附着（2026-08-27 bare 事故：笼统「不在 git 仓库」掩盖 core.bare=true 8 小时）
  echo "不在 git 仓库（诊断: core.bare=$(git config core.bare 2>/dev/null || echo '?') .git=$([ -e .git ] && echo 存在 || echo 缺失)）" >&2
  exit 2
}
FACTORY="$REPO/.factory"
HOST="python3 ${FACTORY}/hosting.py"
# 平台选择与 slug/凭据解析收敛在 hosting.py（ADR-008）；入口一次性探测，
# fail-fast 替代原 slug 预检
${HOST} auth ok >/dev/null 2>&1 || { echo "托管平台不可用（hosting auth：gh 凭据或云效令牌）" >&2; exit 2; }

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
  # 链约定：PR body 含 'Closes #N'（中立 body 由 hosting 归一，两端一致）
  ${HOST} pr list --state open --limit 100 \
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
  ${HOST} issue view "$N" > "$TMP/issue.json" 2>/dev/null \
    || { echo "  issue #$N 不可读，跳过" >&2; return 0; }
  P="$(find_pr_for_issue "$N")"
  if [ -n "$P" ]; then
    ${HOST} pr view "$P" > "$TMP/pr.json"
    ${HOST} label history "$P" > "$TMP/events.json"
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
          ${HOST} issue set-labels "$N" "--${op}" "$label" >/dev/null \
            && echo "  [label] issue $op $label" \
            || echo "  [label] issue $op $label 失败（仅告警）" >&2
        else
          ${HOST} pr set-labels "$P" "--${op}" "$label" >/dev/null \
            && echo "  [label] pr $op $label" \
            || echo "  [label] pr $op $label 失败（仅告警）" >&2
        fi
      done
}

if [ "$TARGET" = "--all" ]; then
  { ${HOST} issue list --state all --limit 200 \
      | python3 -c '
import json, sys
for i in json.load(sys.stdin):
    if any(l.startswith("factory:") for l in i["labels"]):
        print(i["number"])'
    # 零标签 issue 也会被 open PR 关联（链中途死亡 → trap 清标签但 PR 已建），
    # 并入 open PR body 的 Closes 引用（hosting 归一），--all 才能收敛完整
    ${HOST} pr list --state open --limit 100 \
      | python3 -c '
import json, re, sys
for pr in json.load(sys.stdin):
    for m in re.finditer(r"[Cc]loses #(\d+)\b", pr.get("body") or ""):
        print(m.group(1))'; } \
    | sort -un | while read -r N; do sync_one "$N"; done
else
  sync_one "$TARGET"
fi
