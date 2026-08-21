#!/usr/bin/env bash
# validate-pr（S3）：PR 门禁链 —— 人类按下 merge 前的最后一组独立门。
#
# 用法: .factory/validate-pr.sh <pr-number> [--dry-run]
#
# 链: guard(周界) → tests(+证据段) → AI 评审(按触及面选配守卫技能, 并行)
#     → holdout(物理隔离裁决) → 状态标签/评论
# 与 fix-issue 链的会话/进程完全独立（A1：验证者不得共享实现者上下文）。
# 门全过 → label factory:validated + 总结评论；任一门挂 → exit 非零并留
# factory:validation-failed 标签（人类据此决定回炉或驳回）。
set -euo pipefail

PR="${1:-}"
DRY=0
[ "${2:-}" = "--dry-run" ] && DRY=1
if [ -z "${PR}" ]; then
  echo "用法: $0 <pr-number> [--dry-run]" >&2; exit 2
fi

REPO="$(git rev-parse --show-toplevel)"
DIR="${REPO}/.factory/artifacts/pr-${PR}"
node_timeout() { python3 "${REPO}/.factory/factory_lib.py" timeout "$1"; }  # 分级预算：评审15m/holdout 5m

# --- 0. PR 元数据与 diff 面 ---
if [ "${DRY}" = 0 ]; then
  command -v gh >/dev/null || { echo "需要 gh CLI" >&2; exit 2; }
  mkdir -p "${DIR}"
  gh pr view "${PR}" --json number,title,body,headRefName,baseRefName \
    > "${DIR}/pr.json" 2>/dev/null || { echo "PR #${PR} 不存在" >&2; exit 2; }
  BASE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["baseRefName"])' "${DIR}/pr.json")"
  HEAD_REF="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["headRefName"])' "${DIR}/pr.json")"
  CHANGED=(); while IFS= read -r f; do CHANGED+=("${f}"); done < <(gh pr diff "${PR}" --name-only)
else
  BASE="main"; HEAD_REF="<pr-head>"; CHANGED=("<changed-files>")
fi
echo "=== validate-pr #${PR}（${#CHANGED[@]} 文件: ${BASE}...${HEAD_REF}）==="

_node_metric() {  # <node> <t0> <status> → jsonl 行（节点级计时）
  python3 - "$1" "$2" "$3" "$(date +%s)" <<'PYM'
import json, sys
node, t0, status, now = sys.argv[1:5]
print(json.dumps({"node": node, "secs": int(now) - int(t0), "status": status}, ensure_ascii=False))
PYM
}

fail() {  # fail <label> <msg> —— 打标签、留言、退出
  [ "${DRY}" = 0 ] && gh pr edit "${PR}" --add-label factory:validation-failed >/dev/null 2>&1 || true
  echo "✗ $2" >&2; exit "${3:-1}"
}

# --- 1. 周界门（PR 触及面不得进入治理/质检线/发布面） ---
if [ "${DRY}" = 0 ]; then
  python3 "${REPO}/.factory/guard.py" --files "${CHANGED[@]}" \
    || fail gate "周界门拦截（详见上方 guard 输出）" 1
else
  echo "[dry-run] guard.py --files ${CHANGED[*]}"
fi

# --- 2. 测试门 + 证据段（与 fix-issue 同构；产物落 PR 目录） ---
if [ "${DRY}" = 0 ]; then
  if ! (cd "${REPO}" && scripts/run_tests.sh --no-lock) > "${DIR}/tests-output.txt" 2>&1; then
    fail tests "测试门失败（详见 ${DIR}/tests-output.txt）" 1
  fi
  for suite in $(python3 "${REPO}/.factory/factory_lib.py" suites "${CHANGED[@]}"); do
    [ -d "${REPO}/${suite}" ] || continue
    echo "" >> "${DIR}/tests-output.txt"
    echo "── 证据段（verbose）: ${suite}" >> "${DIR}/tests-output.txt"
    (cd "${REPO}" && scripts/run_tests.sh --evidence "${suite}") >> "${DIR}/tests-output.txt" 2>&1 || true
  done
else
  echo "[dry-run] run_tests.sh → ${DIR}/tests-output.txt + 证据段"
fi

# --- 3. AI 评审（按触及面选配；PR 级独立进程，不共享 fix-issue 会话） ---
SKILLS_ARG=""
if [ "${DRY}" = 0 ]; then
  # 命中即评审：skills/<name> 被触 → 对应守卫技能自审；任意 PR 加通用 review
  for skill in api-guard ddl-guard arch-guard impact-guard contract-guard; do
    printf '%s\n' "${CHANGED[@]}" | grep -q "^skills/${skill}/" && SKILLS_ARG="${SKILLS_ARG}${skill} "
  done
fi
echo "==> AI 评审（守卫: ${SKILLS_ARG:-none}；通用 review 常驻）"
if [ "${DRY}" = 1 ]; then
  echo "    [dry-run] omp -p <prompts/pr-review.md + PR diff 内联> --no-session --max-time $(node_timeout pr-review)"
else
  gh pr diff "${PR}" > "${DIR}/pr.diff"
  DIFF="$(cat "${DIR}/pr.diff")"
  TITLE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["title"])' "${DIR}/pr.json")"
  prompt="$(cat "${REPO}/.factory/prompts/pr-review.md")

——PR #${PR}: ${TITLE}
——守卫技能: ${SKILLS_ARG:-无}

——diff 开始——
${DIFF}
——diff 结束——"
  local t0; t0=$(date +%s)
  if ! (cd "${REPO}" && omp -p "${prompt}" --no-session --max-time "$(node_timeout pr-review)" < /dev/null) \
      > "${DIR}/review.log" 2>&1; then
    _node_metric pr-review "${t0}" "fail" >> "${DIR}/node-metrics.jsonl"
    fail review "AI 评审节点失败（详见 ${DIR}/review.log）" 1
  fi
  _node_metric pr-review "${t0}" "ok" >> "${DIR}/node-metrics.jsonl"
  python3 "${REPO}/.factory/factory_lib.py" parse "${DIR}/review.log" "${DIR}/review.json" approve,block \
    || fail review "评审输出无法解析" 1
  [ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "${DIR}/review.json")" = approve ] \
    || fail review "AI 评审 block（详见 ${DIR}/review.json）" 1
fi

# --- 4. holdout（物理隔离终审：PR 标题 + tests-output，正文不进） ---
echo "==> holdout（物理隔离终审）"
if [ "${DRY}" = 1 ]; then
  echo "    [dry-run] omp -p <prompts/holdout.md + title/tests-output> --no-tools --max-time $(node_timeout holdout)"
else
  TITLE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["title"])' "${DIR}/pr.json")"
  OUT="$(cat "${DIR}/tests-output.txt")"
  prompt="$(cat "${REPO}/.factory/prompts/holdout.md")

——issue 编号: PR-${PR}
——issue 标题: ${TITLE}

——tests-output.txt 开始——
${OUT}
——tests-output.txt 结束——"
  local t0; t0=$(date +%s)
  if ! (cd "${REPO}" && omp -p "${prompt}" --no-tools --no-session --max-time "$(node_timeout holdout)" < /dev/null) \
      > "${DIR}/holdout.log" 2>&1; then
    _node_metric holdout "${t0}" "fail" >> "${DIR}/node-metrics.jsonl"
    fail holdout "holdout 节点失败（详见 ${DIR}/holdout.log）" 1
  fi
  _node_metric holdout "${t0}" "ok" >> "${DIR}/node-metrics.jsonl"
  python3 "${REPO}/.factory/factory_lib.py" parse "${DIR}/holdout.log" "${DIR}/holdout.json" PASS,FAIL \
    || fail holdout "holdout 输出无法解析" 1
  [ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "${DIR}/holdout.json")" = PASS ] \
    || fail holdout "holdout=FAIL（详见 ${DIR}/holdout.json）" 1
fi

# --- 5. 通过：状态流转 + 总结评论 ---
if [ "${DRY}" = 0 ]; then
  gh pr edit "${PR}" --remove-label factory:needs-review >/dev/null 2>&1 || true
  gh pr edit "${PR}" --add-label factory:validated >/dev/null 2>&1 || true
  gh pr comment "${PR}" --body "工厂 validate-pr 全门通过（guard + tests + AI 评审 + holdout）。产物: ${DIR}。可合并。" >/dev/null
  echo "✓ PR #${PR} validated（factory:validated）。人类合并。"
else
  echo "[dry-run] label: needs-review → validated + 总结评论"
fi
