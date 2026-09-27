#!/usr/bin/env bash
# fix-issue 全链（S1 人工触发形态；S2 才由 dispatcher 驱动，S1 无 auto-merge）
#
# 用法: .factory/fix-issue.sh <issue-number> [--dry-run]
#
# 链: triage → (accept) → prime → plan → implement ↔ review（ralph 修复轮：
#     review 把可行动发现落 ralph-todo.md，非空即回流 implement 再修再审，
#     ≤FACTORY_RALPH_MAX 轮，默认 2、0=单遍旧行为）→ holdout → PR
# 每节点 = 独立 omp 进程（物理级 fresh context，A1）。
# holdout 与实现链无共享上下文：--no-tools 无工具形态，白名单输入（issue
# 标题 + tests-output.txt）由本脚本内联进 prompt，issue 正文不进验证器。
# 门: implement 后 guard.py（周界）+ 测试门（final_gate_cmd）；holdout FAIL 即停。
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
HOST="python3 ${REPO}/.factory/hosting.py"   # 托管平台抽象（ADR-008）：slug/凭据解析在其内
DIR="${REPO}/.factory/artifacts/issue-${ISSUE}"
BRANCH="factory/issue-${ISSUE}"
WT="${REPO}/.factory/worktrees/issue-${ISSUE}"   # 链独立 worktree（多驱动隔离）
BASE_BRANCH="${FACTORY_BASE_BRANCH:-main}"   # 两级回退：env → main（PR #61 Sourcery 意图；hosting 形态平台配置走 env，forge.json 中间级随 forge 退役）
# 链副作用共享库：issue 评论唯一出口 + 拒绝单一动作（契约见库头注释）
source "${REPO}/.factory/factory-lib.sh"
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
  "factory:needs-human e99695 需人工接管（轮次耗尽/R4熔断）"
  "factory:approved 2cbe4e 审查通过（merge受A5门控）"
  "factory:needs-review 1d76db PR已开待人工审查"
)

ensure_labels() {
  local entry name color desc
  for entry in "${FACTORY_LABELS[@]}"; do
    read -r name color desc <<<"${entry}"
    ${HOST} label ensure "${name}" "${color}" "${desc}" >/dev/null 2>&1 || true
  done
}

issue_label() { # issue_label <add|remove> <name> —— 失败仅告警；租约失效跳写
  # 出口围栏（PR#34 审查修复）：诈尸链的标签写同样有毒，失效即跳写。
  # 跳过而非终止：trap 清理路径必须永不中断（后续台账/回收/放锁依赖顺序）；
  # 被跳过的链由下一处硬围栏（issue_label_swap/issue_comment）或心跳 TERM 终结。
  if ! lease_guard; then
    echo "  [warn] 租约 ${LEASE_KEY:-?} 已失效（epoch=${LEASE_EPOCH:-?}），${1} ${2} 跳过（围栏）" >&2
    return 0
  fi
  if ${HOST} issue set-labels "${ISSUE}" "--${1}" "${2}" >/dev/null 2>&1; then
    echo "  [label] ${1} ${2}"
  else
    echo "  [warn] 标签操作失败：${1} ${2}（可观测性降级，链继续）" >&2
  fi
}

# --- R4 成本熔断：任何 AI 节点/租约/锁副作用之前（fail-closed）---
# DRY 干跑无副作用不检查。退出码 5 = R4 熔断停摆：factory_lib breaker
# 约定码 3 与本脚本「另一链运行中」的 exit 3（下方锁竞争）语义冲突，
# 1/2/4/143 亦已占用，故本地映射为 5；熔断/门故障明细见 breaker.sh 的
# stderr。放行路径零新增副作用，熔断时不写 ledger（无链运行即无成本）。
# 熔断/门故障（3/1）= 机器无法继续、需人工：exit 5 前把 issue 落标
# needs-human（breaker_tripped 边，spec 在 state.py）——否则链死对
# GitHub 侧不可见：S2 下 issue 滞留 in-progress（本点 trap 未装、sync
# 不碰锁）被派发器永久跳过。落标走 issue_label 唯一出口（warn 不
# fail：熔断才是终点，落标失败只降级可观测性）；add 在前、remove 在
# 后——中途断裂 needs-human 也先可见。时序：此刻租约未认领
# （LEASE_KEY 未设，围栏不拦）、EXIT trap 未安装（早期放锁 trap 在
# 下方锁块、主 trap 在预备段）——落标后无人剥除，存续到人工接管。
# 检查点保持在锁获取之前：熔断状态连互斥锁都不占。
if [ "${DRY}" = 0 ]; then
  if ! bash "${REPO}/.factory/breaker.sh" "${REPO}/.factory/locks"; then
    ensure_labels   # 首链即熔断时 needs-human 标签可能尚未建（--force 幂等）
    issue_label add factory:needs-human
    issue_label remove factory:in-progress   # S2 已 claim；S1 零标签，remove-absent 安全
    issue_label remove factory:triaging
    issue_label remove factory:accepted
    exit 5
  fi
fi

# --- 互斥与环境标记（2026-08-21 三链并发事故修复） ---
# D2: 链内所有子进程(omp 节点)可见，仓库 pre-push 钩子据此禁推 main
export FACTORY_CHAIN=1
# D1: S1 手动直跑与 S2 派发器共用 dispatcher 目录锁；派发器子进程
# (FACTORY_DISPATCHED=1)锁已由父持有，重复获取会自锁。
# 锁挂主树 .factory（git-common-dir 锚定，对齐 dispatch.sh 硬锁）：
# 链在独立 worktree 跑后各树 locks/ 互不可见，锁随树走会绕开互斥。
# worktree 隔离落地后 checkout 安全已由分支独占保证，此锁额外序列化
# label 操作与 gate 资源占用（验证 e2e 后可评估放开）
MANUAL_LOCK=0
if [ "${FACTORY_DISPATCHED:-0}" != 1 ] && [ "${DRY}" = 0 ]; then
  MAIN_FACTORY="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null \
    | sed 's#/\.git$##' || true)/.factory"
  LOCKDIR="${MAIN_FACTORY:-${REPO}/.factory}/locks/dispatcher"
  # 父目录预建：下方 mkdir 是单级原子声明（-p 会吞 EEXIST 破坏互斥），
  # 父缺时 ENOENT 被 2>/dev/null 吞成"锁被持"假象（派发器机器 locks/
  # 常驻故未暴露，净克隆首跑必现——源仓 PR#79）
  mkdir -p "${LOCKDIR%/*}" 2>/dev/null || true
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$LOCKDIR/pid"; MANUAL_LOCK=1
  else
    _pid="$(cat "$LOCKDIR/pid" 2>/dev/null || true)"
    if [ -n "${_pid}" ] && ! kill -0 "${_pid}" 2>/dev/null; then
      echo "锁持有者 pid=${_pid} 已死，接管陈锁" >&2
      rm -rf "$LOCKDIR" && mkdir "$LOCKDIR" && echo $$ > "$LOCKDIR/pid" && MANUAL_LOCK=1
    fi
  fi
  [ "${MANUAL_LOCK}" = 1 ] || { echo "dispatcher 或另一链运行中（${LOCKDIR}），稍后再试" >&2; exit 3; }
  # 早期退出(设下方链 trap 前)也要放锁
  trap '[ "${MANUAL_LOCK}" = 1 ] && rm -rf "${LOCKDIR}" 2>/dev/null' EXIT
fi


run_node() {  # run_node <name> — 拼接静态 prompt + 任务参数，独立进程执行
  local name="$1" t0 t1
  echo "==> 节点 ${name}（fresh context 进程，预算 $(node_timeout "${name}")）"
  if [ "${DRY}" = 1 ]; then
    echo "    [dry-run] omp_node <prompts/${name}.md + 任务参数> --max-time $(node_timeout "${name}")"
    echo "    产物: ${DIR}/${name}.(json|md|log)"
    return 0
  fi
  local prompt
  # ADR-009 prompt 参数化：仓库参数（身份/阅读范围/审查依据/final_gate）
  # 从 factory-local.json 注入（fail-closed：repo-vars 失败此处即链终止）。
  prompt="$(cat "${REPO}/.factory/prompts/${name}.md")

$(python3 "${REPO}/.factory/factory_lib.py" repo-vars)

任务参数:
- ISSUE_DIR: ${DIR}
- 仓库根: ${WT}（链独立 worktree，勿越界改主工作区）
- issue 编号: ${ISSUE}
- 节点预算（硬击杀线，编排器 --max-time）: $(node_timeout "${name}")"
  t0=$(date +%s)
  # B1: 节点起点标记（产物 mtime 参照）。创建失败也是节点死亡——先落 node-fail
  # 再退（Sourcery 复审）；DIR 整体不可写时 printf 同败，由 trap 的 chain-abort 兜底
  if ! touch "${DIR}/.${name}-t0" 2>/dev/null; then
    printf 'node-fail %s round=%s node=%s reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND:-0}" "${name}" "marker-create" >> "${DIR}/chain-history" 2>/dev/null || true
    return 1
  fi
  if ! omp_node "${WT}" "${DIR}/${name}.log" "$(node_timeout "${name}")" -- "${prompt}"; then
    _node_metric "${name}" "${t0}" "fail" >> "${DIR}/node-metrics.jsonl"
    printf 'node-fail %s round=%s node=%s reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND:-0}" "${name}" "omp-exit" >> "${DIR}/chain-history" 2>/dev/null || true
    echo "    节点 ${name} 失败（详见 ${DIR}/${name}.log）" >&2; return 1
  fi
  t1=$(date +%s)
  # B1（2026-09-05）：产物判定由"stdout 含 ARTIFACT: 字面行"改为"prompts 声明的
  # 固定产物文件存在且 mtime ≥ 节点起点标记"。容忍 agent 末行格式漂移（实证：计划
  # 完整产出但末行写"产物：/path/plan.json"被 grep 误杀）；产物缺失/未更新仍
  # fail-closed（上一轮残留物 mtime < 起点标记，不误判通过）。无声明节点回退
  # stdout ARTIFACT: 行检查。
  artifact="$(grep -m1 -oE 'ARTIFACT: \$ISSUE_DIR/[^` ]+' "${REPO}/.factory/prompts/${name}.md" | sed 's#.*/##' || true)"
  if [ -z "${artifact}" ]; then
    grep -q "ARTIFACT:" "${DIR}/${name}.log" || {
      _node_metric "${name}" "${t0}" "no-artifact" >> "${DIR}/node-metrics.jsonl"
      printf 'node-fail %s round=%s node=%s reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND:-0}" "${name}" "no-artifact" >> "${DIR}/chain-history" 2>/dev/null || true
      echo "    节点 ${name} 未声明产物（缺 ARTIFACT 行）" >&2; return 1
    }
  elif [ ! -f "${DIR}/${artifact}" ] || [ "${DIR}/${artifact}" -ot "${DIR}/.${name}-t0" ]; then
    _node_metric "${name}" "${t0}" "no-artifact" >> "${DIR}/node-metrics.jsonl"
    printf 'node-fail %s round=%s node=%s reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND:-0}" "${name}" "stale-artifact" >> "${DIR}/chain-history" 2>/dev/null || true
    echo "    节点 ${name} 产物缺失/未更新（${artifact} 不存在或早于节点起点标记）" >&2; return 1
  fi
  _node_metric "${name}" "${t0}" "ok" >> "${DIR}/node-metrics.jsonl"
  printf '    耗时 %ss\n' "$(( t1 - t0 ))"
}

_node_metric() {  # <node> <t0> <status> → jsonl 行（逻辑在 factory_lib metric；ADR-005 下沉）
  python3 "${REPO}/.factory/factory_lib.py" metric "$1" "$2" "$3"
}

json_field() {  # json_field <file> <key> [default] → 键值（逻辑在 factory_lib
  #              jfield；2026-08-28 收口：双引号 -c 内插形态退役，R4 禁形）
  python3 "${REPO}/.factory/factory_lib.py" jfield "$@"
}

run_triage() {  # 物理隔离裁决器：--no-tools --no-session，输入全部内联
  echo "==> 节点 triage（物理隔离：--no-tools，白名单内联）"
  if [ "${DRY}" = 1 ]; then
    echo "    [dry-run] omp_node <prompts/triage.md + 内联 MISSION/issue 标题正文> --no-tools --config .factory/omp-isolated.yml --max-time $(node_timeout triage)"
    echo "    产物: ${DIR}/triage.(json|log)"
    return 0
  fi
  local mission title body cmts prompt
  mission="$(cat "${REPO}/MISSION.md")"
  title="$(json_field "${DIR}/issue.json" title)"
  body="$(json_field "${DIR}/issue.json" body "")"
  # 评论是重投/整改指令的载体（holdout FAIL 后人类补充验收标准等），
  # 物理隔离裁决器无工具，必须内联；最新 3 条足够传达整改上下文
  cmts="$(python3 - "${DIR}/issue.json" <<'PYC'
import json, sys
d = json.load(open(sys.argv[1]))
cs = d.get("comments") or []
out = "\n\n".join("[作者: %s]\n%s" % (c.get("author") or "?", c["body"]) for c in cs[-3:])
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
  if ! omp_node "${REPO}" "${DIR}/triage.log" "$(node_timeout triage)" --no-tools \
      --config "${REPO}/.factory/omp-isolated.yml" -- "${prompt}"; then
    _node_metric triage "${t0}" "fail" >> "${DIR}/node-metrics.jsonl"
    printf 'node-fail %s round=%s node=%s reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND:-0}" "triage" "omp-exit" >> "${DIR}/chain-history" 2>/dev/null || true
    echo "    triage 节点失败（详见 ${DIR}/triage.log）" >&2; return 1
  fi
  _node_metric triage "${t0}" "ok" >> "${DIR}/node-metrics.jsonl"
  python3 "${REPO}/.factory/factory_lib.py" parse "${DIR}/triage.log" "${DIR}/triage.json" accept,reject \
    || { printf 'node-fail %s round=%s node=%s reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND:-0}" "triage" "parse" >> "${DIR}/chain-history" 2>/dev/null || true; \
         echo "    triage 输出无法解析为 JSON（见 factory_lib.parse_agent_json）" >&2; return 1; }
}

run_holdout() {  # 物理隔离验证器：--no-tools + 输入全部内联，agent 无任何工具
  echo "==> 节点 holdout（物理隔离：--no-tools，白名单内联）"
  if [ "${DRY}" = 1 ]; then
    echo "    [dry-run] omp_node <prompts/holdout.md + 内联 title/tests-output> --no-tools --config .factory/omp-isolated.yml --max-time $(node_timeout holdout)"
    echo "    产物: ${DIR}/holdout.json"
    return 0
  fi
  local title out
  title="$(json_field "${DIR}/issue.json" title)"
  out="$(cat "${DIR}/tests-output.txt")"
  local prompt
  prompt="$(cat "${REPO}/.factory/prompts/holdout.md")

——issue 编号: ${ISSUE}
——issue 标题: ${title}

——tests-output.txt 开始——
${out}
——tests-output.txt 结束——"
  local t0; t0=$(date +%s)
  if ! omp_node "${REPO}" "${DIR}/holdout.log" "$(node_timeout holdout)" --no-tools \
      --config "${REPO}/.factory/omp-isolated.yml" -- "${prompt}"; then
    _node_metric holdout "${t0}" "fail" >> "${DIR}/node-metrics.jsonl"
    printf 'node-fail %s round=%s node=%s reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND:-0}" "holdout" "omp-exit" >> "${DIR}/chain-history" 2>/dev/null || true
    echo "    holdout 节点失败（详见 ${DIR}/holdout.log）" >&2; return 1
  fi
  _node_metric holdout "${t0}" "ok" >> "${DIR}/node-metrics.jsonl"
  python3 "${REPO}/.factory/factory_lib.py" parse "${DIR}/holdout.log" "${DIR}/holdout.json" PASS,FAIL \
    || { printf 'node-fail %s round=%s node=%s reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND:-0}" "holdout" "parse" >> "${DIR}/chain-history" 2>/dev/null || true; \
         echo "    holdout 输出无法解析为 JSON（见 factory_lib.parse_agent_json）" >&2; return 1; }
}


# --- 预备：拉取 issue 原文（唯一一次读不可信文本的地方，落盘供节点读） ---
if [ "${DRY}" = 0 ]; then
  ${HOST} auth ok >/dev/null 2>&1 || { echo "托管平台不可用（hosting auth）" >&2; exit 2; }
  mkdir -p "${DIR}"
  ${HOST} issue view "${ISSUE}" > "${DIR}/issue.json" 2>/dev/null \
    || { echo "issue #${ISSUE} 不存在或不可读" >&2; exit 2; }
  # fail-closed：rc=0 但输出为空/非 JSON 的 gh（网络截断、代理 stub 等）不可信——
  # 空数据流入 triage 会产出"空 issue 拒绝"+毒回执（2026-08-23 实证；彼时
  # run_triage 尚处 `|| exit 1` 条件上下文、set -e 体内豁免，json_field 崩溃
  # 被吞成空串。豁免面已由裸调用纪律根治，本守卫保留为纵深防御+精确报错）
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("title") else 3)' \
    "${DIR}/issue.json" 2>/dev/null || { echo "issue.json 无效（空/非 JSON/无 title），链终止" >&2; exit 2; }
  # --- 租约认领（多写者仲裁，2026-08-24；README「租约仲裁」）---
  # 认领失败（他机链持有未过期租约 / 仲裁不可达 / 单写者本地锁被占）
  # = 链终止——降级裸跑等于重新打开多写者竞态。SUPABASE_DB 未设 = 显式
  # 单写者形态：claim 走本地锁降级（同机互斥生效、跨机无保护，README
  # 「单写者降级」）。LEASE_KEY/LEASE_EPOCH 是 factory-lib.sh 出口围栏的
  # 上下文：被夺/吊销的诈尸链在 label/评论出口被拒，秒级残窗由回执幂等键
  # 兜底。claim 放在首个 issue 侧副作用（打 triaging）之前。
  LEASE_KEY="issue:${ISSUE}"
  LEASE_EPOCH="$(lease_claim "${LEASE_KEY}")" \
    || { echo "[error] 租约 ${LEASE_KEY} 认领失败，fail-closed 终止（README「租约仲裁」）" >&2; exit 4; }
  # 心跳失约（被夺/吊销/过期）即被后台循环 TERM：exit 143 触发 EXIT trap 级联
  # （台账/清标/worktree 回收/放租约）。此处到 trap 升级之间无可失败语句，
  # 残余窗口由租约自然过期（默认 900s）自愈。
  trap "exit 143" TERM   # 双引号：test_fix_issue_trap 的 trap 提取正则按 ' EXIT 锚定，单引号形态会被截胡
  lease_heartbeat_loop "${LEASE_KEY}" "${LEASE_EPOCH}"
  echo "  [lease] ${LEASE_KEY} epoch=${LEASE_EPOCH} 已认领（心跳 ${FACTORY_HB_INTERVAL:-60}s）"
  ensure_labels
  issue_label add factory:triaging
  # 轮次：同 issue 的第 N 次链（chain-history 计数；首轮通过率的分母）
  ROUND=$(( $(grep -c 'chain-start' "${DIR}/chain-history" 2>/dev/null || echo 0) + 1 ))
  # 清上一轮裁决产物：防陈旧 triage.json/holdout.json 污染本轮判定与台账分类
  rm -f "${DIR}/triage.json" "${DIR}/holdout.json"
  # 归档上一轮过程产物 → *-pre-r${ROUND}.*（A：跨轮回流，下轮 prime/plan 的
  # 增量输入。上轮死在更早节点时文件属更早轮——pre-rN 语义 =「本轮开始时的
  # 内容」仍为真；B1 判定不受影响：归档即移走，旧文件不可能冒充本轮产物）
  for _af in prime.md plan.json implement.md review.md; do
    if [ -f "${DIR}/${_af}" ]; then
      mv -f "${DIR}/${_af}" "${DIR}/${_af%.*}-pre-r${ROUND}.${_af##*.}" || true
    fi
  done
  CHAIN_T0=$(date +%s)
  echo "chain-start $(date -u +%Y-%m-%dT%H:%M:%SZ) round=${ROUND}" >> "${DIR}/chain-history"
  # 台账（EXIT 时写）：{ts, issue, round, type, exit, secs}——重派率/首轮通过率 jq 一行可算。
  # type: rejected=triage 拒绝；否则按分支 diff 分类（doc/code/test/mixed）
  write_ledger() {
    local rc=$1 kind
    if [ -f "${DIR}/triage.json" ] && [ "$(json_field "${DIR}/triage.json" verdict 2>/dev/null)" = reject ]; then
      kind=rejected
    else
      local -a files=()
      local f
      # || true 吞 exit code（无 merge-base 等场景）但保留 stdout——吞错必须在
      # 命令替换层，防 set -e 在 EXIT trap 内杀死 write_ledger（#23 根因；
      # 曾误写 `| true`：diff 输出喂给 true，changed 恒空，台账全记 no-diff，
      # PR #9 审查评论1）
      # NUL 分隔读入数组（bash 3.2 无 mapfile）：文件名含空白/通配符不拆分
      # （源仓#70 审查）；classify 失败降级 no-diff，trap 不因分类器死
      while IFS= read -r -d '' f; do files+=("$f"); done \
        < <(git -C "${REPO}" diff --name-only -z ${BASE_BRANCH}..."${BRANCH}" 2>/dev/null || true)
      [ "${#files[@]}" -eq 0 ] && while IFS= read -r -d '' f; do files+=("$f"); done \
        < <(git -C "${REPO}" diff --name-only -z HEAD~1 2>/dev/null || true)
      if [ "${#files[@]}" -gt 0 ]; then
        kind="$(python3 "${REPO}/.factory/factory_lib.py" classify "${files[@]}")" || kind=no-diff
      else
        kind=no-diff
      fi
    fi
    mkdir -p "${REPO}/.factory/locks"
    # issue 值加引号：Codeup 编号是字符串（T-18），%s 裸出产出
    # {"issue": T-18} 非法 JSON，jq 消费方崩（下游仓实测）
    printf '{"ts": "%s", "issue": "%s", "round": %s, "type": "%s", "exit": %s, "secs": %s}\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ISSUE}" "${ROUND}" "${kind}" "${rc}" \
      "$(( $(date +%s) - CHAIN_T0 ))" >> "${REPO}/.factory/locks/ledger.jsonl"
  }
  # #14 补遗：抢救未提交 WIP——rev-list=0 时 trap 的 salvage push 无物可推
  # （#165 r1-r3 实证：implement 未提交即死，WIP 随 worktree 强删湮灭）。
  # intent-to-add 让 untracked 入 diff；binary diff 快照到 ISSUE_DIR 供下轮
  # implement 作证据输入（只读参考，不自动续作）；空 diff 不留噪声文件。
  # best-effort：恒 return 0，任何失败不中断清理链（#23 纪律）。
  salvage_wip() {
    local rc="$1" patch
    if [ "${rc}" -eq 0 ] || [ ! -d "${WT}" ]; then return 0; fi
    patch="${DIR}/salvage-r${ROUND}.patch"
    git -C "${WT}" add -N . >/dev/null 2>&1 || true
    if ! git -C "${WT}" diff HEAD --binary > "${patch}" 2>/dev/null || [ ! -s "${patch}" ]; then
      rm -f "${patch}" 2>/dev/null || true
    else
      echo "  [salvage] 未提交 WIP 快照 → ${patch}"
    fi
    return 0
  }
  # 失败清理 + 台账 + 产出抢救 + worktree 回收：
  # - set +e 首动作（#23）：trap 是状态机复位的唯一保障，内部任一命令
  #   非零不得中止清理链——trap 失败模式收敛为"多打日志"而非"静默中断"
  #   （源仓#57 实证：write_ledger 内 git 竞态 141 → 标签/worktree/
  #   台账三重残留 → 队列死锁）
  # - 失败且分支有新提交 → push 抢救产出（#14：否则随 worktree 强删 +
  #   下轮 -B 重置回基线孤儿化，implement 成果湮灭）。--force：下轮
  #   从基线重跑后非 FF，远端镜像语义 = 最新一轮产出；推送失败仅告警
  #   不阻断后续清理（网络故障不应二次放大为状态残留）
  # - rc≠0 追加 chain-abort 行到 chain-history（A：下轮 prime/plan 的死因
  #   输入）；未提交 WIP 由 salvage_wip 快照到 ISSUE_DIR，均须先于 worktree
  #   强删。SIGKILL 下 trap 整体失守，此通道同殁——dispatcher 侧检测为
  #   残余缺口，另行立项
  # - 非零退出移除流转标签回零标签态（可重试）；无论成败都记账；
  #   worktree 无论成败一并回收
  # - 清理顺序（PR#34 审查修复）：标签清理在 lease_cleanup **之前**——清标
  #   也是副作用出口，须持有效租约过围栏；先放租约会让正常失败链的清标被拒
  #   （标签滞留）。被夺/吊销链的清标被围栏跳过是正确行为：标签归新属主，
  #   或作为人工债务可见。lease_cleanup 收心跳+放租约，放清理链末尾。
  # D1: 本 trap 覆盖早期放锁 trap，故自带锁释放；派发链 MANUAL_LOCK=0 不动锁
  # shellcheck disable=SC2154  # rc 于本 trap 行内由 rc=$? 赋值，shellcheck 不解析 trap 字符串
  trap 'rc=$?; set +e; write_ledger "${rc}"; if [ "${rc}" -ne 0 ]; then printf "chain-abort %s round=%s exit=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${ROUND}" "${rc}" >> "${DIR}/chain-history" 2>/dev/null || true; fi; if [ "${rc}" -ne 0 ] && [ "$(git -C "${REPO}" rev-list --count ${BASE_BRANCH}.."${BRANCH}" 2>/dev/null || echo 0)" -gt 0 ]; then git -C "${REPO}" push --force --no-verify origin "${BRANCH}" >/dev/null 2>&1 && echo "  [salvage] 失败链产出已推送 origin/${BRANCH}" || echo "  [warn] 失败链产出推送失败，产出仅在本地分支 ${BRANCH}" >&2; fi; salvage_wip "${rc}"; git -C "${REPO}" worktree remove --force "${WT}" >/dev/null 2>&1 || true; [ "${rc}" -ne 0 ] && { issue_label remove factory:triaging; issue_label remove factory:accepted; issue_label remove factory:in-progress; }; lease_cleanup; [ "${MANUAL_LOCK}" = 1 ] && rm -rf "${LOCKDIR:-}" 2>/dev/null' EXIT
else
  echo "[dry-run] hosting issue view #${ISSUE} → ${DIR}/issue.json"
  echo "[dry-run] label: +factory:triaging（裁决后 → accepted|rejected）"
fi

echo "=== fix-issue #${ISSUE} → ${DIR} ==="
# --- 1. triage ---
# 调用纪律（set-e 豁免面修复，2026-08-23）：节点函数必须**裸调用**。
# `run_X || exit 1` 把函数置于条件上下文，set -e 在其体内整体失效——
# 中间赋值失败（cat/json_field 崩溃）被吞成空串继续跑，triage 拿垃圾输入
# 产出毒裁决（#59 空 issue.json 实证）。裸调用下 set -e 管函数体内每一步；
# 函数内显式 return 1 语义不变（顶层简单命令失败即触发 errexit + EXIT trap）。
run_triage
if [ "${DRY}" = 0 ]; then
  VERDICT="$(json_field "${DIR}/triage.json" verdict)"
  if [ "${VERDICT}" = accept ]; then
    # S1/S2 互斥: in-progress 双标签 + dispatch.sh accepted 队列显式跳过
    # in-progress 条目（gh label 过滤是"含有"非"仅有"，2026-08-21 实证双派）。
    # rejected 同步自清：重投（补充上下文后移除标签重跑链）被 accept 时，
    # 上轮 rejected 残留会让三标签并存、成功合并的 issue 永久挂 rejected
    # （closed 清理只保留 rejected——残留即被当作裁决记录）。remove-absent
    # 安全（首轮无此标签，同 :249 模式）
    issue_label_swap "factory:triaging,factory:rejected" "factory:accepted,factory:in-progress" || exit 1
  else
    # 链是 in-progress 生命周期终点；S1 无此标签，remove-absent 安全。
    # 落标 + 判据回执一次收口（回执语义/失败分级见 factory-lib.sh）
    issue_reject "factory:triaging,factory:in-progress" "${DIR}/triage.json" || exit 1
    echo "triage=${VERDICT}，链终止"
    exit 0
  fi

fi
# --- 2-4. prime → plan → implement（同一分支上顺序执行） ---
if [ "${DRY}" = 0 ]; then
  # 链独立 worktree: 主 worktree 永不切分支, 多链并行天然安全, 人工会话零冲突。
  # 分支若被其他 worktree 持有则 add 失败(宁死勿抢, 防误伤人工现场)
  git -C "${REPO}" worktree remove --force "${WT}" >/dev/null 2>&1 || true
  git -C "${REPO}" worktree prune
  git -C "${REPO}" worktree add -B "${BRANCH}" "${WT}" "${BASE_BRANCH}" >/dev/null
fi
run_node prime
run_node plan

# --- 4-5. implement ↔ review（ralph 修复轮）---
# review 把可行动发现落盘 ralph-todo.md；脚本以文件非空为确定性回流信号：
# 非空 → 再跑 implement（消化清单）→ review（重审重写清单）→ ……
# 清单空（或轮次耗尽）→ 放行，残留发现随 review.md 进 PR 交人类。
# 终止判断是文件非空检查，零 LLM 决策（铁律 4 同源）。
RALPH=0
RALPH_MAX="${FACTORY_RALPH_MAX:-2}"
case "${RALPH_MAX}" in
  ''|*[!0-9]*) echo "FACTORY_RALPH_MAX 须为非负整数（得到: ${RALPH_MAX}）" >&2; exit 2 ;;
esac
rm -f "${DIR}/ralph-todo.md"
while :; do
  run_node implement
  run_node review
  if [ "${DRY}" = 1 ]; then
    break   # 干跑单遍，保持旧输出形态
  fi
  if [ "${RALPH_MAX}" -gt 0 ] && [ -s "${DIR}/ralph-todo.md" ] && [ "${RALPH}" -lt "${RALPH_MAX}" ]; then
    RALPH=$((RALPH + 1))
    echo "    [ralph] review 存在可行动发现（ralph-todo.md）→ 修复轮 ${RALPH}/${RALPH_MAX}"
    continue
  fi
  if [ -s "${DIR}/ralph-todo.md" ]; then
    echo "    [ralph] 修复轮耗尽，残留发现随 review.md 进 PR（人类裁决）"
  fi
  break
done

# --- 5.5 未提交改动机械收编（review 修复纪律的脚本兜底）---
# gate/holdout 验证工作区，push 只发 HEAD——不收编则「验证态 ≠ 发布态」，
# 修复以工作区态存在即随 worktree 清理丢失（issue #63 实证：target_file
# 契约修复因此丢失，origin 分支缺字段）。收编先于 guard --files 的
# BASE...BRANCH 计算，周界检查因此覆盖全部实际改动（含兜底提交）。
if [ "${DRY}" = 0 ] && [ -n "$(git -C "${WT}" status --porcelain)" ]; then
  echo "    [backstop] 工作区有未提交改动，机械收编（节点应自行提交，见 prompts/review.md 纪律）："
  git -C "${WT}" status --porcelain | sed 's/^/      /'
  git -C "${WT}" add -A \
    && git -C "${WT}" commit -m "chore(chain): 机械收编链内未提交改动（backstop；节点应自行提交）" \
    || { echo "backstop 提交失败（hook 拒绝？），链终止" >&2; exit 1; }
fi

# --- 6. 确定性门：周界 + 测试（tests-output.txt 由脚本生成，不依赖节点自觉） ---
if [ "${DRY}" = 0 ]; then
  # NUL 分隔读入数组（bash 3.2 无 mapfile，同 trap 段先例）：换行
  # 分隔 + 未引号展开会把含空格/通配符路径拆碎（web-tools#5 Sourcery）
  CHANGED=()
  while IFS= read -r -d '' f; do CHANGED+=("${f}"); done \
    < <(git -C "${WT}" diff --name-only -z "${BASE_BRANCH}...${BRANCH}" 2>/dev/null \
    || git -C "${WT}" diff --name-only -z HEAD~1)

  # 权威改动面判定（#170 评审修正）：CHANGED 空还可能源于 diff 命令静默
  # 失败（三点式 2>/dev/null 与 HEAD~1 兜底双败），不可与真零改动混同。
  # log 失败 = 改动面不可判定 → fail-closed；guard 跳过与 §7.5 收官共用
  # 本值，不二次取样。
  COMMITS="$(git -C "${WT}" log --oneline "${BASE_BRANCH}..${BRANCH}")" \
    || { echo "[zero-diff] git log ${BASE_BRANCH}..${BRANCH} 失败：改动面不可判定，fail-closed 终止" >&2; exit 1; }
  if [ "${#CHANGED[@]}" -gt 0 ]; then
    python3 "${REPO}/.factory/guard.py" --files ${CHANGED[@]+"${CHANGED[@]}"}
  elif [ -n "${COMMITS}" ]; then
    # 有提交却收不到 diff：diff 收集异常，保持既有 fail-closed 不变量
    # （旧路径死于 guard exit 2，此处显式退出并说明原因）。
    echo "[guard] CHANGED 空但 ${BASE_BRANCH}..${BRANCH} 有提交：diff 收集异常，fail-closed 终止" >&2
    exit 1
  else
    # 零改动轮（issue #165 round-4 实证）：bash 3.2 空数组经 ${CHANGED[@]+…}
    # 展开消失，`--files` 零路径 = 用法错误 → guard fail-closed exit 2 误杀
    # 全绿链。零改动 = 无周界面可查，跳过 guard。
    echo "[guard] 零改动轮：无周界面可查，guard 跳过"
  fi
  # ADR-009 门命令数据化：final_gate_cmd 来自 factory-local.json（fail-closed：
  # factory_lib 加载失败此处即非零终止）；read -ra 拆词为 argv 数组执行。
  GATE_CMD="$(python3 "${REPO}/.factory/factory_lib.py" final-gate)"
  read -r -a GATE_ARGS <<< "${GATE_CMD}"
  if ! (cd "${WT}" && "${GATE_ARGS[@]}") > "${DIR}/tests-output.txt" 2>&1; then
    echo "测试门失败（详见 ${DIR}/tests-output.txt）" >&2; exit 1
  fi
  # docstring 门（可选门：docstring_gate_cmd 未配置 → 空输出跳过；配置损坏
  # → factory_lib fail-closed 非零终止）。对外 API 100% + 内部 ≥80% 阈值
  # 由各仓检查器自定；产物独立落 docstring-output.txt，不污染测试证据。
  DG_CMD="$(python3 "${REPO}/.factory/factory_lib.py" docstring-gate)"
  if [ -n "${DG_CMD}" ]; then
    read -r -a DG_ARGS <<< "${DG_CMD}"
    if ! (cd "${WT}" && "${DG_ARGS[@]}") > "${DIR}/docstring-output.txt" 2>&1; then
      echo "docstring 门失败（详见 ${DIR}/docstring-output.txt）" >&2; exit 1
    fi
  fi
  # 证据段：触及的测试套件以 -v 重跑附于末尾——holdout 不许推测，
  # 需要可引用的测试名/参数化用例名（-q 点号无法建立诉求对应关系）
  # NUL 分隔消费（PR #116）：套件名可含空格（skills/foo bar/...），for 词拆分
  # 会拆碎名致证据段静默跳过；suites 产出 NUL → read -d '' 逐条保真
  while IFS= read -r -d '' suite; do
    [ -d "${WT}/${suite}" ] || continue
    echo "" >> "${DIR}/tests-output.txt"
    echo "── 证据段（verbose）: ${suite}" >> "${DIR}/tests-output.txt"
    (cd "${WT}/${suite}" && python3 -m pytest -o addopts="" -v) >> "${DIR}/tests-output.txt" 2>&1 || true
  done < <(python3 "${REPO}/.factory/factory_lib.py" suites ${CHANGED[@]+"${CHANGED[@]}"})
else
  echo "[dry-run] guard.py --files <changed> + 测试门(final_gate_cmd) → ${DIR}/tests-output.txt（脚本生成）"
  echo "[dry-run] docstring 门（docstring_gate_cmd，未配置则跳过） → ${DIR}/docstring-output.txt"
fi

# --- 7. holdout（独立验证；输入白名单见 prompt） ---
run_holdout
if [ "${DRY}" = 0 ]; then
  # 裁决按 round 存档（失败证据永不覆盖丢失；下轮 prime 回流的输入源）
  python3 - "${DIR}" "${ROUND}" <<'PYA' >> "${DIR}/chain-history"
import json, sys, pathlib
d = json.loads(pathlib.Path(sys.argv[1], "holdout.json").read_text())
verdict = d.get("verdict") if isinstance(d, dict) else None
evidence = d.get("evidence") if isinstance(d, dict) else None
# parse_agent_json 只验 verdict；evidence 缺失时裸取会 KeyError 在
# verdict 检查前炸链且 chain-history 无记录（PR #9 审查评论3）。
# malformed 也先留档再 fail-closed——失败证据不可静默丢失
if verdict not in ("PASS", "FAIL") or not isinstance(evidence, str) or not evidence:
    print(f"holdout round={sys.argv[2]} verdict={verdict} evidence=<malformed>")
    raise SystemExit("holdout 结果缺 verdict/evidence 字段")
print(f"holdout round={sys.argv[2]} verdict={verdict} evidence={evidence[:200]}")
PYA
  [ "$(json_field "${DIR}/holdout.json" verdict)" = PASS ] \
    || { echo "holdout=FAIL，链终止（不建 PR；evidence 已存 chain-history）"; exit 1; }
fi

# --- 7.5 零改动轮收官：无 diff 即无 PR（issue #165 round-4 实证） ---
# 纯验证轮的产出是工件与 issue 评论，不是代码。若继续走 §8，push 会把
# BASE_BRANCH 领先 origin 的提交整段带进 PR diff（如未推的 main 提交），
# 污染人类评审面。holdout PASS 后零提交 → exit 0 收官：rc=0 不触发
# trap 清标，accepted/in-progress 留守，派发器按设计跳过滞留
# in-progress 的 issue（见文件头 S2 注释），验证轮不再被重派。
if [ "${DRY}" = 0 ] && [ -z "${COMMITS}" ]; then
  echo "[zero-diff] 本轮零仓内改动（纯验证轮，holdout 已 PASS）：不 push、不建 PR，exit 0 收官。"
  # 终态可见性（2026-09-15 issue #165 实证）：留守 in-progress 在 GitHub 侧
  # 无任何痕迹，人类看不见链已收官。终态评论补痕；幂等键防诈尸残窗重发。
  # 评论失败仅告警——链已 PASS，可见性是透明度而非门。
  cat > "${DIR}/zero-diff-receipt.md" <<RECEIPT
零改动验证轮收官：链内全门 + holdout PASS，无代码改动，不建 PR。

issue 保持 \`factory:accepted\` + \`factory:in-progress\` 留守防重派（§7.5）。
若本 issue 为日回归容器（标题含 [factory-regression]），后续日回归失败时
滞留态将被自动唤醒重派；其余 issue 的留守请人工裁决处置。
若本诉求已满足，请人工确认后关闭本 issue。
RECEIPT
  issue_comment "${DIR}/zero-diff-receipt.md" \
    "factory:receipt:issue-${ISSUE}:r${ROUND}-zero-diff" \
    || echo "  [warn] 终态评论失败（${DIR}/zero-diff-receipt.md 留档），不影响收官" >&2
  exit 0
fi
# --- 8. 开 PR（S1 到此为止：merge 由人类决定，铁律 5） ---
if [ "${DRY}" = 0 ]; then
  # --no-verify：新分支首推无 @{push}，lefthook {push_files} 模板必然 exit 128；
  # 链内等价门（测试门/guard/holdout）已在本链跑过，此处跳过的是
  # 与链重复的人工推送门，非绕过验证
  git -C "${WT}" push -u origin "${BRANCH}" --no-verify
  # 标题取 HEAD 提交主题（原 gh --fill 的平台特例，中立化：链自控输入）
  PR_TITLE="$(git -C "${WT}" log --pretty=%s -1)"
  ${HOST} pr create \
    --head "$BRANCH" --title "$PR_TITLE" \
    --base "${BASE_BRANCH}" \
    --body-file <(echo "Closes #${ISSUE}"; echo; echo "工厂链产物见 ${DIR}"; echo; echo "链: triage → prime → plan → implement ↔ review（ralph ≤${RALPH_MAX} 轮）→ guard → holdout") \
    --label "factory:needs-review" \
  # PR 落地后 issue 侧转移：accepted → in-review（PR 状态接管 issue，§7）。
  # in-progress 由链属主自清：锁不进 PR 阶段，避免 in-review+in-progress
  # 双标签滞留到 closed（锁单一属主原则，链是 in-progress 生命周期的终点）
  issue_label_swap "factory:accepted,factory:in-progress" "factory:in-review" || exit 1
  echo "PR 已建（factory:needs-review）。issue #${ISSUE} → factory:in-review。人类合并。"
else
  echo "[dry-run] push + hosting pr create --label factory:needs-review；issue: accepted → in-review"
fi

