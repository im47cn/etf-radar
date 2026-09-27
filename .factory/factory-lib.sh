#!/usr/bin/env bash
# factory-lib.sh — 链脚本共享库（source 引入，勿直接执行）。
# 与 factory_lib.py 命名成对：py 侧管解析/渲染/净化，本库管链对 issue
# 副作用的收口。调用方契约：source 前已定义 REPO / ISSUE（ADR-008 起
# REPO_SLUG 不再需要——托管平台选择收敛在 hosting.py）。
# 收口不变量（新增写点必须复用，不得旁路；详见 README 架构段）：
# 1. 链写 issue 评论唯一出口 = issue_comment()：发送前 factory_lib sanitize
#    原地中和正文中的 [factory:rejected] 子串。
# 2. 拒绝 = 单一动作 issue_reject()：落标与判据回执评论一次收口。两入口
#    （fix-issue.sh 链 / triage-batch.sh 批次）曾各自只做一半——#59 二次
#    拒绝静默实证：散落的动作必然被漏做一半。
# 3. 租约围栏（2026-08-24 多写者化）：链副作用出口（label/评论）在发送前
#    校验租约 epoch——被接管/吊销的诈尸链在出口被拒，秒级残窗由评论
#    幂等键兜底。LEASE_KEY 未设（无租约上下文）不拦。
# 4. 托管平台层级（ADR-008）：hosting.py 仅是本库的下层传输——issue 评论/
#    标签副作用唯一出口仍是 issue_comment()/issue_label_swap()（sanitize+
#    租约围栏在出口统一管），链/批次脚本不得绕过本库直调 hosting 写 issue
#    副作用（gauntlet lint-factory-hosting-exit 门机械化盯防）。
source "${REPO}/.factory/factory-lease.sh"

omp_node() { # omp_node <cwd> <log> <timeout> [omp-opts...] -- <prompt...>
  # omp CLI 唯一执行点（ADR-009 引擎收口，设计 §4 runNode 的 bash 形态）：
  # 链/批次/PR 门/反哺全部节点经此 spawn——换引擎（SDK 直连等）只改本函数。
  # 契约：--no-session 恒加（物理级 fresh context，A1）；--no-extensions 恒加
  # （扩展发现把无头 -p 节点 hook 进 feishu 网关 attach：恒定 ~19s 附加税，且
  # attach 劣化即整预算静默死锁——#165 r2/r3 review 连挂实证，空 diff 也烧满
  # 17m 零输出；--no-extensions 后平凡探针 7.9s。显式 -e 不受影响，launchd
  # 网关 daemon 独立托管亦不受影响）；--max-time 必填；
  # opts 透传（--no-tools / --config …）；prompt 为 "--" 之后的剩余参数整体。
  # 返回 omp 进程退出码（调用方自持 metric/失败语义）。
  local _cwd="$1" _log="$2" _tmo="$3"
  shift 3
  local -a _opts=()
  while [ "${1:-}" != "--" ]; do
    [ "$#" -gt 0 ] || { echo "[error] omp_node: 缺 -- 分隔符" >&2; return 2; }
    _opts+=("$1"); shift
  done
  shift
  (cd "${_cwd}" && omp -p "$*" --no-session --no-extensions ${_opts[@]+"${_opts[@]}"} \
      --max-time "${_tmo}" < /dev/null) > "${_log}" 2>&1
}


issue_label_swap() { # issue_label_swap <"删,删"|空> <"加,加"> —— 单请求原子转移
  # 逐个 add/remove 会把状态机跳变拆成可失败的顺序依赖（半途断裂=双标签或裸奔）；
  # 单请求换标签消除顺序问题。失败 return 1，终止语义由调用方决定
  # （链：exit 1 → EXIT trap 清理 + factory-state.sh sync 兜底；批次：告警下一 issue）。
  # 出口围栏：租约失效（被夺/吊销）即拒绝——标签是投影，但诈尸写投影同样有毒。
  # ADR-008：平台调用经 hosting.py（GitHub 单请求原子；Codeup 无 issue 面）。
  lease_guard || {
    echo "[error] 租约 ${LEASE_KEY:-?} 已失效（epoch=${LEASE_EPOCH:-?}），标签转移拒绝" >&2
    return 1
  }
  local -a args=("issue" "set-labels" "${ISSUE}")
  [ -n "${1:-}" ] && args+=(--remove "${1}")
  [ -n "${2:-}" ] && args+=(--add "${2}")
  local err
  if err="$(python3 "${REPO}/.factory/hosting.py" "${args[@]}" 2>&1 >/dev/null)"; then
    echo "  [label] -${1:-} +${2}"
  else
    # stderr 落档（#207 实证：>/dev/null 2>&1 把 HostingError 里的 gh
    # 失败原因吞掉，[error] 行无从排查）——hosting 侧原因回显在错误行下。
    echo "[error] 标签转移失败：-${1:-} +${2}（issue #${ISSUE}）" >&2
    [ -n "${err}" ] && printf '  [hosting] %s\n' "${err}" >&2
    return 1
  fi
}

issue_comment() { # issue_comment <body-file> [dedupe-marker] —— 链写 issue 评论的唯一出口
  # 安全不变量在出口：发送前 factory_lib sanitize 原地中和正文中的
  # [factory:rejected] 子串——链产正文（LLM reasons 等）可能回显用户评论
  # 里的标记，state.py 子串扫描会把携带标记的链评论当人工覆盖、永久钉死
  # rejected。渲染器不各自记得，出口统一管。中和失败 fail-closed 不发送
  # （防毒丸放出），正文文件保留供排查。
  #
  # 幂等键（可选第二参）：正文尾埋 <!-- marker --> 并发送前查重——
  # fence_check 与平台调用之间的秒级残窗里，诈尸链可能重复发回执；
  # 命中即视为已发送（return 0），漏网代价从"重复评论"降为"无"。
  # 标记刻意不含 [factory:rejected] 子串（sanitize/state.py 双通道安全）。
  # ADR-008：marker 查重与埋入收敛在 hosting.py issue comment --marker。
  python3 "${REPO}/.factory/factory_lib.py" sanitize "${1}" || {
    echo "  [warn] 评论正文标记中和失败（${1}），不发送" >&2; return 1; }

  lease_guard || {
    echo "[error] 租约 ${LEASE_KEY:-?} 已失效（epoch=${LEASE_EPOCH:-?}），评论拒绝" >&2
    return 1
  }
  if [ -n "${2:-}" ]; then
    python3 "${REPO}/.factory/hosting.py" issue comment "${ISSUE}" \
      --body-file "${1}" --marker "${2}"
  else
    python3 "${REPO}/.factory/hosting.py" issue comment "${ISSUE}" --body-file "${1}"
  fi
}

issue_reject() { # issue_reject <remove-csv|空> <triage.json> —— 拒绝的单一动作
  # 落标（→ factory:rejected）+ 判据回执评论，一次收口：
  #   <remove-csv>  落标同时原子移除的标签。链入口传 "factory:triaging,
  #                 factory:in-progress"；批次入口（零标签 issue）传 ""
  #   <triage.json> 判据源；回执渲染于同目录 reject-receipt.md
  # 失败语义分两级：落标调用失败先复核远端标签态（#207 实证：gh 非零
  # 但标签已落远端——退出码 ≠ 落定事实），factory:rejected 确在列即按
  # 已落定继续回执，确证缺失才 return 1（裁决未落定，调用方终止/跳过）；
  # 回执生成/评论失败仅告警——裁决已由标签落定，回执是透明度而非门，
  # 正文留档可手动补发。评论经 issue_comment 唯一出口，标记中和不因入口
  # 不同而绕过；回执刻意不含裸标记——标记评论通道保留给人类手动覆盖。
  # 回执带幂等键：同轮次重放（诈尸残窗/人工重跑）查重跳过；链侧带轮次
  # ROUND、批次侧固定 rbatch（r 前缀恒在，ROUND 缺省展开 batch）——同
  # issue 两入口的回执键天然互不冲突。
  local marker="factory:receipt:issue-${ISSUE}:r${ROUND:-batch}"
  local dir
  dir="$(dirname "$2")"
  if ! issue_label_swap "${1:-}" "factory:rejected"; then
    # 假阴性复核（#207：mutation landed + client reported failure——
    # 2026-09-20 11:01:01Z 标签已落 GitHub 而 gh 报非零）：落标调用失败
    # ≠ 裁决未落定。factory:rejected 在远端 = 裁决已生效，回执必须跟上
    # （steering 审查报告规范：只落标不发判据 = 不可审计的静默拒绝）；
    # 确证缺失才按未落定终止。
    if ! python3 "${REPO}/.factory/hosting.py" issue get-labels "${ISSUE}" 2>/dev/null \
        | grep -q '"factory:rejected"'; then
      return 1
    fi
    echo "  [warn] 落标调用失败但 factory:rejected 已在远端（issue #${ISSUE}）——按已落定继续回执" >&2
  fi
  if python3 "${REPO}/.factory/factory_lib.py" receipt "$2" \
      > "${dir}/reject-receipt.md" 2>/dev/null; then
    if issue_comment "${dir}/reject-receipt.md" "${marker}" >/dev/null 2>&1; then
      echo "  [receipt] 拒绝回执已评论到 issue #${ISSUE}"
    else
      echo "  [warn] 拒绝回执评论失败，正文在 ${dir}/reject-receipt.md（可手动补发）" >&2
    fi
  else
    echo "  [warn] 拒绝回执生成失败（triage.json 解析异常），跳过评论" >&2
  fi
}
