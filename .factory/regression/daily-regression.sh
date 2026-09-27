#!/usr/bin/env bash
# daily-regression.sh — 自挖掘日回归（借鉴 dark-factory comprehensive-test 模式；
# 2026-08-25 周频提至日频：停摆/断档类故障的发现延迟从 ≤7d 收到 ≤1d）。
#
# 三层顺序执行（全部跑完不短路——三层结果表完整是 triage 的输入）：
#   1. badcase-strict : python3 scripts/badcase_runner.py --strict-exact
#                       （发版回归级：期望↔实际双向精确比对）
#   2. gauntlet       : sh tools/gauntlet.sh
#                       （全量门禁唯一入口，见 docs/design/spec-2026-08-21-gauntlet-entry.md）
#   3. doc-freshness  : python3 tools/check_doc_freshness.py
#                       （陈述↔事实一致性 R1-R9（语义见 tools/check_doc_freshness.py 头注释）；gauntlet 内已有同名子层，
#                        独立成层是为了单层日志与失败归因）
#   4. dispatch-liveness: python3 .factory/regression/dispatch_liveness.py
#                       （调度器活性：停摆标记在=FAIL；streak 文件超 26h
#                        未更新=LaunchAgent 断档 FAIL——两种死法都抓）
#
# 失败 → 开 issue：标题 [factory-regression] <date> 日回归失败：<首失败层>；
#   已有 open 的标题含 [factory-regression] 的 issue → 按标签态路由（幂等，
#   wake=移除留守的 in-progress 唤醒重派 / new=rejected 后另开 / append=评论追加；
#   经 factory-lib issue_comment 收口出口，ADR-008 层级契约）。
# 全绿 → 追加一行 JSON 到 .factory/metrics/daily-regression.jsonl。
#
# 标签策略（有意零标签）：triage-batch.sh 只拾取零 factory:* 标签的 open issue，
# dispatch.sh 消费 factory:accepted——零标签让回归 issue 走设计的
# 「写 issue → 工厂自动看见」路径（triage 裁决 → accepted → 链修复）。
# 打 factory:accepted 会绕过 triage 裁决；打其他 factory:* 会永远不被拾取。
#
# 日志契约：.factory/artifacts/regression/<YYYY-MM-DD>/<HHMMSS>/<层名>.log
#   （每次运行独立目录，不覆盖——同日重跑保留全部证据，diff 相邻两次可测
#    flake；latest 符号链接指向最近一次）。
#
# 用法:
#   bash .factory/regression/daily-regression.sh            # 真跑（失败开 issue / 全绿记 metrics）
#   bash .factory/regression/daily-regression.sh --dry-run  # 真跑三层，只预览将开的 issue，不写 gh、不记 metrics
#
# 退出码: 0=全绿（或锁被持静默退出） 1=有层失败（issue 已开/已评） 2=基础设施错误
set -euo pipefail

# ── 环境（launchd/cron 无 PATH；形态对齐 cron-dispatch.sh） ──────────────
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME="${HOME:?launchd/cron 环境未设置 HOME}"

DRY_RUN=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "未知参数: ${a}（仅支持 --dry-run）" >&2; exit 2 ;;
  esac
done

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SELF/../.." && pwd)"
cd "$REPO"
FACTORY="$REPO/.factory"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 托管平台（ADR-008）：slug/凭据解析收敛 hosting.py；仅失败路径写平台时
# 需要，dry-run 不依赖
HOST="python3 ${FACTORY}/hosting.py"

# ── 单实例锁（mkdir 原子性 + PID 活性检测，形态对齐 dispatch.sh；
#    防手动跑与 launchd 定时跑并发执行 gauntlet 互踩 .coverage 清理） ────
LOCKDIR="$FACTORY/locks/daily-regression"
mkdir -p "${LOCKDIR%/*}" 2>/dev/null || true
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  _pid="$(cat "$LOCKDIR/pid" 2>/dev/null || true)"
  if [ -n "$_pid" ] && ! kill -0 "$_pid" 2>/dev/null; then
    echo "[$(ts)] 锁持有者 pid=${_pid} 已死，接管陈锁" >&2
    rm -rf "$LOCKDIR"
    mkdir "$LOCKDIR"
  else
    echo "[$(ts)] 另一日回归实例运行中（pid=${_pid}），退出" >&2
    exit 0
  fi
fi
echo $$ > "$LOCKDIR/pid"
BODY="$(mktemp)"
trap 'rm -f "$BODY" 2>/dev/null; rm -rf "$LOCKDIR" 2>/dev/null' EXIT

# ── 三层执行（输出全量落日志） ──────────────────────────────────────────
DATE="$(date +%F)"
RUN_STAMP="$(date +%H%M%S)"
LOG_DIR="$FACTORY/artifacts/regression/$DATE/$RUN_STAMP"
mkdir -p "$LOG_DIR" "$FACTORY/metrics"
# 最近一次运行的稳定入口；-n 确保 latest 已是符号链接时整体替换而非穿入
ln -sfn "$DATE/$RUN_STAMP" "$FACTORY/artifacts/regression/latest"

LAYER_NAMES=() LAYER_STATUS=() LAYER_RC=()

run_layer() {  # <name> <cmd...>
  local name="$1"; shift
  local rc=0
  echo "── [$(ts)] $name 开始"
  "$@" > "$LOG_DIR/$name.log" 2>&1 || rc=$?
  LAYER_NAMES+=("$name")
  LAYER_RC+=("$rc")
  if [ "$rc" -eq 0 ]; then
    LAYER_STATUS+=(pass)
    echo "── [$(ts)] $name PASS → $LOG_DIR/$name.log"
  else
    LAYER_STATUS+=(fail)
    echo "── [$(ts)] $name FAIL（rc=${rc}）→ $LOG_DIR/$name.log" >&2
  fi
}

run_layer badcase-strict python3 scripts/badcase_runner.py --strict-exact
run_layer gauntlet sh tools/gauntlet.sh
run_layer doc-freshness python3 tools/check_doc_freshness.py
run_layer dispatch-liveness python3 .factory/regression/dispatch_liveness.py

FIRST_FAIL=""
TABLE=""
for i in "${!LAYER_NAMES[@]}"; do
  st="✅ PASS"
  [ "${LAYER_STATUS[$i]}" = pass ] || st="❌ FAIL (rc=${LAYER_RC[$i]})"
  TABLE+="$(printf '| %s | %s | `%s` |\n' \
    "${LAYER_NAMES[$i]}" "$st" "$LOG_DIR/${LAYER_NAMES[$i]}.log")"
  if [ -z "$FIRST_FAIL" ] && [ "${LAYER_STATUS[$i]}" = fail ]; then
    FIRST_FAIL="${LAYER_NAMES[$i]}"
  fi
done

# ── 全绿：metrics 台账（dry-run 预演不记账） ───────────────────────────
if [ -z "$FIRST_FAIL" ]; then
  echo "── [$(ts)] 四层全绿"
  if [ "$DRY_RUN" = 1 ]; then
    echo "── [$(ts)] dry-run：跳过 metrics 追加与 gh 写操作"
  else
    printf '{"ts":"%s","result":"pass","layers":{"badcase-strict":"pass","gauntlet":"pass","doc-freshness":"pass","dispatch-liveness":"pass"}}\n' \
      "$(date +%Y-%m-%dT%H:%M:%S%z)" >> "$FACTORY/metrics/daily-regression.jsonl"
  fi
  exit 0
fi

# ── 失败：汇总 issue（首失败层 + 该层日志尾部 30 行） ────────────────────
TITLE="[factory-regression] ${DATE} 日回归失败：${FIRST_FAIL}"
{
  echo "自动化日回归失败（首失败层：\`${FIRST_FAIL}\`）。"
  echo
  echo "- 日期：${DATE}"
  echo "- HEAD：$(git rev-parse --short HEAD)（运行于工作树，未自动提交）"
  echo
  echo "## 三层结果"
  echo
  echo "| 层 | 结果 | 日志 |"
  echo "|---|---|---|"
  printf '%s' "$TABLE"
  echo
  echo "## \`${FIRST_FAIL}.log\` 尾部 30 行"
  echo
  echo '```'
  tail -n 30 "$LOG_DIR/$FIRST_FAIL.log" || true
  echo '```'
  echo
  echo "## 复跑"
  echo
  echo '```bash'
  echo "cd $REPO && bash .factory/regression/daily-regression.sh"
  echo '# 或只预览不开 issue：bash .factory/regression/daily-regression.sh --dry-run'
  echo '```'
  echo
  echo "## 验收（可机械判定）"
  echo
  echo "- [ ] 复跑 \`bash .factory/regression/daily-regression.sh\` 全绿"
  echo "- [ ] 首失败层 \`${FIRST_FAIL}.log\` 根因在本仓修复或裁决为环境噪音（评论留痕）"
} > "$BODY"

if [ "$DRY_RUN" = 1 ]; then
  echo "── [$(ts)] dry-run：将开的 issue 标题："
  echo "     ${TITLE}"
  echo "── [$(ts)] dry-run：正文预览："
  cat "$BODY"
  exit 1
fi

[ "$(${HOST} auth ok >/dev/null 2>&1; echo $?)" = 0 ] || { echo "托管平台不可用（hosting auth）" >&2; exit 2; }

# 幂等：已有 open 的 [factory-regression] issue → 按 routing 投递（见
# factory_lib regression_routing：wake|new|append），不重复开
EXISTING_JSON="$(${HOST} issue list --state open --limit 200 \
  | python3 -c '
import json, sys
for i in json.load(sys.stdin):
    if "[factory-regression]" in (i.get("title") or ""):
        print(json.dumps(i)); break')" \
  || { echo "hosting issue list 失败（网络/权限）" >&2; exit 2; }
EXISTING="$(printf '%s' "$EXISTING_JSON" \
  | python3 -c 'import json,sys
s = sys.stdin.read()
print(json.loads(s)["number"] if s.strip() else "")')"
if [ -n "$EXISTING" ]; then
  # L2 滞留接线（2026-09-15 issue #165 实证）：in-progress 滞留 → 唤醒
  # 重派；rejected → 开新容器；其余追加。决策纯函数化（含租约存活态
  # 四路由），负控制见 .factory/tests/test_regression_routing.py
  # 租约存活：PG 形态（SUPABASE_DB）租约在库中，本地不可判 → 保守
  # unknown（不自动唤醒）；单写者形态经 factory_lib lease-fresh 判锁
  # 文件存活（SIGKILL 残锁过期同判死）
  LEASE_STATE=unknown
  if [ -z "${SUPABASE_DB:-}" ]; then
    if python3 "$FACTORY/factory_lib.py" lease-fresh \
        "$FACTORY/locks/leases/issue:${EXISTING}.lock"; then
      LEASE_STATE=alive
    else
      LEASE_STATE=dead
    fi
  fi
  ROUTE="$(printf '%s' "$EXISTING_JSON" \
    | python3 "$FACTORY/factory_lib.py" regression-routing "$LEASE_STATE" \
    || { echo "regression-routing 失败" >&2; exit 2; })"
  if [ "$ROUTE" = wake ]; then
    echo "── [$(ts)] 回归 issue #${EXISTING} 滞留 in-progress（零改动轮留守/链早亡），唤醒重派"
    ISSUE="$EXISTING" REPO="$REPO" bash -c '
      source "${0}/factory-lib.sh"
      issue_label_swap "factory:in-progress" ""
    ' "$FACTORY" \
      || echo "  [warn] 唤醒（移除 in-progress）失败，仍评论追加——人工处置" >&2
    printf '\n> 唤醒：上一容器滞留 in-progress（无存活链租约），本次失败时已移除该标签，\n> 下轮 dispatch 将重新派发链修复本次结果。\n' >> "$BODY"
  elif [ "$ROUTE" = live ]; then
    echo "── [$(ts)] 回归 issue #${EXISTING} 链在途（in-progress + 租约存活/形态未知），不唤醒仅追加"
  elif [ "$ROUTE" = new ]; then
    echo "── [$(ts)] 回归 issue #${EXISTING} 已 rejected（人工判噪音），新失败开新容器"
    printf '\n> 注：上一回归容器 #%s 已被人工 rejected，本 issue 为新失败另开。\n' "$EXISTING" >> "$BODY"
    EXISTING=""
  else
    echo "── [$(ts)] 已有 open 回归 issue #${EXISTING}，评论追加本次结果"
  fi
fi
if [ -n "$EXISTING" ]; then
  # 收口出口（ADR-008 层级契约）：sanitize（防日志回显 [factory:rejected] 标记
  # 钉死 issue）+ 租约围栏（无租约上下文时直通）都在 factory-lib 出口统一管
  ISSUE="$EXISTING" REPO="$REPO" bash -c '
    source "${0}/factory-lib.sh"
    issue_comment "$1"
  ' "$FACTORY" "$BODY" \
    || { echo "issue_comment（factory-lib 收口出口）失败（网络/权限）" >&2; exit 2; }
else
  URL="$(${HOST} issue create --title "$TITLE" --body-file "$BODY" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("url") or "")')" \
    || { echo "hosting issue create 失败（网络/权限）" >&2; exit 2; }
  echo "── [$(ts)] 已开回归 issue：${URL}"
fi
exit 1
