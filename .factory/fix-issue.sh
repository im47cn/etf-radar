#!/usr/bin/env bash
# fix-issue 全链（S1 人工触发形态；S2 才由 dispatcher 驱动，S1 无 auto-merge）
#
# 用法: .factory/fix-issue.sh <issue-number> [--dry-run]
#
# 链: triage → (accept) → prime → plan → implement → review → holdout → PR
# 每节点 = 独立 omp 进程（物理级 fresh context，A1）。
# holdout 与实现链无共享上下文：--no-tools 无工具形态，白名单输入（issue
# 标题 + tests-output.txt）由本脚本内联进 prompt，issue 正文不进验证器。
# 门: implement 后 guard.py（周界）+ run_tests.sh（测试）；holdout FAIL 即停。
# 预算: 每节点 omp --max-time（默认 30m，可 env 覆盖）。
# 残留通道（诚实声明）: 会话 hooks/memory 注入仍在；S2 以 SDK inMemory 收口。
set -euo pipefail

ISSUE="${1:-}"
DRY=0
[ "${2:-}" = "--dry-run" ] && DRY=1
if [ -z "${ISSUE}" ]; then
  echo "用法: $0 <issue-number> [--dry-run]" >&2; exit 2
fi

REPO="$(git rev-parse --show-toplevel)"
REPO_SLUG="${GH_REPO:-$(git -C "$(dirname "$0")/.." remote get-url origin 2>/dev/null \
  | sed -E 's#.*github\.com[:/]##; s#\.git$##')}"
DIR="${REPO}/.factory/artifacts/issue-${ISSUE}"
BRANCH="factory/issue-${ISSUE}"
node_timeout() { python3 "${REPO}/.factory/factory_lib.py" timeout "$1"; }  # 分级预算：裁决器5m/工作节点15m/implement 30m
# --- 状态机标签：S1 issue 侧 triaging → accepted|rejected → in-review；S2 加
#     in-progress（dispatcher 抢占锁）与 PR 侧 needs-fix/needs-human/approved。
#     完整转移表唯一权威在 state.py TRANSITIONS；标签派生/收敛见 factory-state.sh ---
FACTORY_LABELS=(
  "factory:triaging fbca04 工厂链triage裁决中"
  "factory:accepted 0e8a16 triage通过，待派发"
  "factory:rejected d73a4a triage拒绝，链已终止"
  "factory:in-review 5319e7 PR已开，issue状态由PR接管"
  "factory:in-progress d4c5f9 dispatcher已抢占，链运行中"
  "factory:needs-fix fbca04 PR被打回待修（≤2轮）"
  "factory:needs-human e99695 轮次耗尽，人工接管"
  "factory:approved 2cbe4e 审查通过（merge受A5门控）",
  "factory:needs-review 1d76db PR已开待人工审查"
)

ensure_labels() {
  local entry name color desc
  for entry in "${FACTORY_LABELS[@]}"; do
    read -r name color desc <<<"${entry}"
    gh label create "${name}" --color "${color}" --description "${desc}" --force >/dev/null 2>&1 || true
  done
}

issue_label() { # issue_label <add|remove> <name> —— 失败仅告警
  if gh issue edit "${ISSUE}" --"${1}-label" "${2}" >/dev/null 2>&1; then
    echo "  [label] ${1} ${2}"
  else
    echo "  [warn] 标签操作失败：${1} ${2}（可观测性降级，链继续）" >&2
  fi
}

issue_label_swap() { # issue_label_swap <"删,删"> <"加,加"> —— 单请求原子转移，失败链终止
  # 逐个 add/remove 会把状态机跳变拆成可失败的顺序依赖（半途断裂=双标签或裸奔）；
  # 单请求换标签消除顺序问题。失败非零退出，由 EXIT trap 清理、factory-state.sh sync 兜底。
  if gh issue edit "${ISSUE}" --remove-label "${1}" --add-label "${2}" >/dev/null 2>&1; then
    echo "  [label] -${1} +${2}"
  else
    echo "[error] 标签转移失败：-${1} +${2}（issue #${ISSUE}），链终止" >&2
    exit 1
  fi
}


run_node() {  # run_node <name> — 拼接静态 prompt + 任务参数，独立进程执行
  local name="$1" t0 t1
  echo "==> 节点 ${name}（fresh context 进程，预算 $(node_timeout "${name}")）"
  if [ "${DRY}" = 1 ]; then
    echo "    [dry-run] omp -p <prompts/${name}.md + 任务参数> --max-time $(node_timeout "${name}")"
    echo "    产物: ${DIR}/${name}.(json|md|log)"
    return 0
  fi
  local prompt
  prompt="$(cat "${REPO}/.factory/prompts/${name}.md")

任务参数:
- ISSUE_DIR: ${DIR}
- 仓库根: ${REPO}
- issue 编号: ${ISSUE}"
  t0=$(date +%s)
  if ! (cd "${REPO}" && omp -p "${prompt}" --no-session --max-time "$(node_timeout "${name}")" < /dev/null) \
      > "${DIR}/${name}.log" 2>&1; then
    _node_metric "${name}" "${t0}" "fail" >> "${DIR}/node-metrics.jsonl"
    echo "    节点 ${name} 失败（详见 ${DIR}/${name}.log）" >&2; return 1
  fi
  t1=$(date +%s)
  if ! grep -q "ARTIFACT:" "${DIR}/${name}.log"; then
    _node_metric "${name}" "${t0}" "no-artifact" >> "${DIR}/node-metrics.jsonl"
    echo "    节点 ${name} 未声明产物（缺 ARTIFACT 行）" >&2; return 1
  fi
  _node_metric "${name}" "${t0}" "ok" >> "${DIR}/node-metrics.jsonl"
  printf '    耗时 %ss\n' "$(( t1 - t0 ))"
}

_node_metric() {  # _node_metric <node> <t0> <status> → jsonl 行（节点级计时数据源）
  python3 - "$1" "$2" "$3" "$(date +%s)" <<'PYM'
import json, sys
node, t0, status, now = sys.argv[1:5]
print(json.dumps({"node": node, "secs": int(now) - int(t0), "status": status}, ensure_ascii=False))
PYM
}

json_field() {  # json_field <file> <python-expr-on-d>
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1"
}

run_triage() {  # 物理隔离裁决器：--no-tools --no-session，输入全部内联
  echo "==> 节点 triage（物理隔离：--no-tools，白名单内联）"
  if [ "${DRY}" = 1 ]; then
    echo "    [dry-run] omp -p <prompts/triage.md + 内联 MISSION/issue 标题正文> --no-tools --max-time $(node_timeout triage)"
    echo "    产物: ${DIR}/triage.(json|log)"
    return 0
  fi
  local mission title body cmts prompt
  mission="$(cat "${REPO}/MISSION.md")"
  title="$(json_field "${DIR}/issue.json" 'd["title"]')"
  body="$(json_field "${DIR}/issue.json" 'd.get("body") or ""')"
  # 评论是重投/整改指令的载体（holdout FAIL 后人类补充验收标准等），
  # 物理隔离裁决器无工具，必须内联；最新 3 条足够传达整改上下文
  cmts="$(python3 - "${DIR}/issue.json" <<'PYC'
import json, sys
d = json.load(open(sys.argv[1]))
cs = d.get("comments") or []
out = "\n\n".join("[作者: %s]\n%s" % (c["author"]["login"], c["body"]) for c in cs[-3:])
print(out if out else "（无评论）")
PYC
)"
  prompt="$(cat "${REPO}/.factory/prompts/triage.md")

——MISSION.md 开始——
${mission}
——MISSION.md 结束——

——issue #${ISSUE} 标题: ${title} 正文开始——
${body}
——正文结束——

——issue 评论开始（最新 3 条；含整改/重投指令时以评论为准）——
${cmts}
——评论结束——"
  local t0; t0=$(date +%s)
  if ! (cd "${REPO}" && omp -p "${prompt}" --no-tools --no-session --max-time "$(node_timeout triage)" < /dev/null) \
      > "${DIR}/triage.log" 2>&1; then
    _node_metric triage "${t0}" "fail" >> "${DIR}/node-metrics.jsonl"
    echo "    triage 节点失败（详见 ${DIR}/triage.log）" >&2; return 1
  fi
  _node_metric triage "${t0}" "ok" >> "${DIR}/node-metrics.jsonl"
  python3 "${REPO}/.factory/factory_lib.py" parse "${DIR}/triage.log" "${DIR}/triage.json" accept,reject \
    || { echo "    triage 输出无法解析为 JSON（见 factory_lib.parse_agent_json）" >&2; return 1; }
}

run_holdout() {  # 物理隔离验证器：--no-tools + 输入全部内联，agent 无任何工具
  echo "==> 节点 holdout（物理隔离：--no-tools，白名单内联）"
  if [ "${DRY}" = 1 ]; then
    echo "    [dry-run] omp -p <prompts/holdout.md + 内联 title/tests-output> --no-tools --max-time $(node_timeout holdout)"
    echo "    产物: ${DIR}/holdout.json"
    return 0
  fi
  local title out
  title="$(json_field "${DIR}/issue.json" 'd["title"]')"
  out="$(cat "${DIR}/tests-output.txt")"
  local prompt
  prompt="$(cat "${REPO}/.factory/prompts/holdout.md")

——issue 编号: ${ISSUE}
——issue 标题: ${title}

——tests-output.txt 开始——
${out}
——tests-output.txt 结束——"
  local t0; t0=$(date +%s)
  if ! (cd "${REPO}" && omp -p "${prompt}" --no-tools --no-session --max-time "$(node_timeout holdout)" < /dev/null) \
      > "${DIR}/holdout.log" 2>&1; then
    _node_metric holdout "${t0}" "fail" >> "${DIR}/node-metrics.jsonl"
    echo "    holdout 节点失败（详见 ${DIR}/holdout.log）" >&2; return 1
  fi
  _node_metric holdout "${t0}" "ok" >> "${DIR}/node-metrics.jsonl"
  python3 "${REPO}/.factory/factory_lib.py" parse "${DIR}/holdout.log" "${DIR}/holdout.json" PASS,FAIL \
    || { echo "    holdout 输出无法解析为 JSON（见 factory_lib.parse_agent_json）" >&2; return 1; }
}


# --- 预备：拉取 issue 原文（唯一一次读不可信文本的地方，落盘供节点读） ---
if [ "${DRY}" = 0 ]; then
  command -v gh >/dev/null || { echo "需要 gh CLI" >&2; exit 2; }
  mkdir -p "${DIR}"
  gh issue view "${ISSUE}" --json number,title,body,comments > "${DIR}/issue.json" 2>/dev/null \
    || { echo "issue #${ISSUE} 不存在或不可读" >&2; exit 2; }
  ensure_labels
  issue_label add factory:triaging
  # 失败清理：非零退出时移除流转标签，issue 回到零 factory 标签态（可重试/人工接手）
  trap 'rc=$?; [ $rc -ne 0 ] && { issue_label remove factory:triaging; issue_label remove factory:accepted; issue_label remove factory:in-progress; }' EXIT
else
  echo "[dry-run] gh issue view #${ISSUE} → ${DIR}/issue.json"
  echo "[dry-run] label: +factory:triaging（裁决后 → accepted|rejected）"
fi

echo "=== fix-issue #${ISSUE} → ${DIR} ==="
# --- 1. triage ---
run_triage || exit 1
if [ "${DRY}" = 0 ]; then
  VERDICT="$(json_field "${DIR}/triage.json" 'd["verdict"]')"
  if [ "${VERDICT}" = accept ]; then
    # S1/S2 互斥: in-progress 使 dispatcher 队列(只认 accepted)与
    # needs-fix 重派(跳过 in-progress)都不会重复认领本 issue
    issue_label_swap "factory:triaging" "factory:accepted,factory:in-progress"
  else
    issue_label_swap "factory:triaging" "factory:rejected"
    echo "triage=${VERDICT}，链终止"
    exit 0
  fi

fi
# --- 2-4. prime → plan → implement（同一分支上顺序执行） ---
[ "${DRY}" = 0 ] && git -C "${REPO}" checkout -B "${BRANCH}" main
run_node prime    || exit 1
run_node plan     || exit 1
run_node implement|| exit 1

# --- 5. review ---
run_node review   || exit 1

# --- 6. 确定性门：周界 + 测试（tests-output.txt 由脚本生成，不依赖节点自觉） ---
if [ "${DRY}" = 0 ]; then
  CHANGED="$(git -C "${REPO}" diff --name-only main..."${BRANCH}" 2>/dev/null \
    || git -C "${REPO}" diff --name-only HEAD~1)"
  python3 "${REPO}/.factory/guard.py" --files ${CHANGED}
  if ! (cd "${REPO}" && scripts/run_tests.sh --no-lock) > "${DIR}/tests-output.txt" 2>&1; then
    echo "测试门失败（详见 ${DIR}/tests-output.txt）" >&2; exit 1
  fi
  # 证据段：触及的测试套件以 -v 重跑附于末尾——holdout 不许推测，
  # 需要可引用的测试名/参数化用例名（-q 点号无法建立诉求对应关系）
  for suite in $(python3 "${REPO}/.factory/factory_lib.py" suites ${CHANGED}); do
    [ -d "${REPO}/${suite}" ] || continue
    echo "" >> "${DIR}/tests-output.txt"
    echo "── 证据段（verbose）: ${suite}" >> "${DIR}/tests-output.txt"
    (cd "${REPO}" && scripts/run_tests.sh --evidence "${suite}") >> "${DIR}/tests-output.txt" 2>&1 || true
  done
else
  echo "[dry-run] guard.py --files <changed> + run_tests.sh → ${DIR}/tests-output.txt（脚本生成）"
fi

# --- 7. holdout（独立验证；输入白名单见 prompt） ---
run_holdout || exit 1
if [ "${DRY}" = 0 ]; then
  [ "$(json_field "${DIR}/holdout.json" 'd["verdict"]')" = PASS ] \
    || { echo "holdout=FAIL，链终止（不建 PR）"; exit 1; }
fi

# --- 8. 开 PR（S1 到此为止：merge 由人类决定，铁律 5） ---
if [ "${DRY}" = 0 ]; then
  # --no-verify：新分支首推无 @{push}，lefthook {push_files} 模板必然 exit 128；
  # 链内等价门（run_tests.sh/guard/holdout）已在本链跑过，此处跳过的是
  # 与链重复的人工推送门，非绕过验证
  git -C "${REPO}" push -u origin "${BRANCH}" --no-verify
  # --repo/--head 显式指定：origin 的 fetch URL 是 codeup，gh 无法从
  # remote 解析 GitHub 仓库（dispatch5 实测 "could not resolve remote origin"）
  gh pr create --repo "$REPO_SLUG" --head "$BRANCH" --fill \
    --label "factory:needs-review" \
    --body-file <(echo "Closes #${ISSUE}"; echo; echo "工厂链产物见 ${DIR}"; echo; echo "链: triage → prime → plan → implement → review → guard → holdout")
  # PR 落地后 issue 侧转移：accepted → in-review（PR 状态接管 issue，§7）。
  # in-progress 由链属主自清：锁不进 PR 阶段，避免 in-review+in-progress
  # 双标签滞留到 closed（锁单一属主原则，链是 in-progress 生命周期的终点）
  issue_label_swap "factory:accepted,factory:in-progress" "factory:in-review"
  echo "PR 已建（factory:needs-review）。issue #${ISSUE} → factory:in-review。人类合并。"
else
  echo "[dry-run] push + gh pr create --label factory:needs-review；issue: accepted → in-review"
fi

