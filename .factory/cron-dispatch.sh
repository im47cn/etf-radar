#!/bin/sh
# cron 包装器：cron 环境无 PATH/git/gh/omp —— 在此显式注入。
# 互斥：macOS 无 flock，用原生 shlock（.factory/locks/dispatch.lock）。
# 日志固定尾追 .factory/locks/dispatch.log（gitignored）。
set -u
SELF=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
REPO=$(CDPATH='' cd -- "$(dirname -- "$SELF")/.." && pwd)
LOG="${REPO}/.factory/locks/dispatch.log"
LOCK="${REPO}/.factory/locks/dispatch.lock"
METRICS="${REPO}/.factory/metrics"
STREAK="${REPO}/.factory/locks/dispatch-fail-streak"
STALLED_MARK="${METRICS}/dispatch-stalled"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$REPO" || { echo "无法进入 ${REPO}" >&2; exit 2; }
export PATH HOME="${HOME:?cron 环境未设置 HOME}"
mkdir -p "${REPO}/.factory/locks"  # 净克隆首跑：目录 gitignored 不存在时 shlock 建锁 ENOENT 被误读为锁被持而静默退出（源仓 PR#79 审查）；下方日志重定向同依赖此目录
# 运行时状态自举：locks/ gitignored，不随分发/仓库移动到达；缺失时 breaker
# fail-closed 静默停摆（源仓 2026-09-01 实证）。floor 是静态配置，
# 缺失自举默认值；ledger 是 R4 成本账本——_load_ledger 对缺失文件返回 []
# （breaker 按空账本放行），缺失与空账本语义等价。2026-09-01 用户要求
# "先帮我处理（自愈）"：缺失自动建空账本消除告警，留痕（stderr + LOG）
# 供审计（此消息不含 "ledger.jsonl 缺失" 连续串，聚合层 grep 不命中）。
[ -f "${REPO}/.factory/locks/floor.json" ] || printf '{\n  "max_runs_per_day": 10,\n  "max_consecutive_failures": 3\n}\n' > "${REPO}/.factory/locks/floor.json"
[ -f "${REPO}/.factory/locks/ledger.jsonl" ] || {
  : > "${REPO}/.factory/locks/ledger.jsonl"
  msg="$(date '+%Y-%m-%d %H:%M:%S') 成本账本缺失已自愈：重建空 ledger.jsonl（R4 成本账本从零累计）"
  echo "$msg" >&2
  echo "$msg" >> "${LOG}" 2>/dev/null || true
}
ts() { date '+%Y-%m-%d %H:%M:%S'; }
# 抢锁；持锁进程已死则清锁重试一次（防 stale lock 卡死调度）
if ! /usr/bin/shlock -f "$LOCK" -p $$; then
  OPID=$(cat "$LOCK" 2>/dev/null || :)
  if [ -n "$OPID" ] && ! kill -0 "$OPID" 2>/dev/null; then
    rm -f "$LOCK"
    /usr/bin/shlock -f "$LOCK" -p $$ || exit 0
  else
    exit 0
  fi
fi
trap 'rm -f "$LOCK"' EXIT INT TERM
{
  # R4 成本熔断（fail-closed）：本 wrapper 先跑 triage-batch 再跑 dispatch，
  # dispatch.sh 入口另有同款门——此处为 triage 批次而设（cron 路径的
  # LLM 裁决在 dispatch 之前跑）。退出码透传 breaker.sh（3=熔断），
  # 停摆信息随块重定向落 dispatch.log。
  bash "${REPO}/.factory/breaker.sh" "${REPO}/.factory/locks" || exit $?
  echo "── $(ts) triage 批次开始"
  "${REPO}/.factory/triage-batch.sh" && rc=0 || rc=$?
  echo "── $(ts) triage 批次结束（exit=${rc}）"
  echo "── $(ts) dispatch 开始"
  "${REPO}/.factory/dispatch.sh"; drc=$?
  echo "── $(ts) dispatch 结束（exit=${drc}）"
  # 停摆可见性（2026-08-25 ssh.github.com slug 回归：LaunchAgent 每轮
  # exit 2 静默停摆 4h 无人察觉——日志是唯一信号，没人盯日志）。仅计
  # exit 2（环境/配置错误：非 git/无 slug/无 gh/MAX_PARALLEL 非法）；
  # breaker rc 3 是 R4 的显式停机语义，不计。连击 ≥3 轮（默认 45min
  # @600s 间隔）写标记；恢复（rc 0）清零并摘标记。
  if [ "$drc" -eq 2 ]; then
    n=$(cat "$STREAK" 2>/dev/null || echo 0)
    n=$((n + 1)); printf '%s\n' "$n" > "$STREAK"
    if [ "$n" -ge "${DISPATCH_STALLED_N:-3}" ]; then
      mkdir -p "$METRICS"
      # 环境自检快照随标记落盘 + macOS 桌面通知（2026-08-27 bare 事故：
      # 仅文件标记无人盯，主仓 core.bare=true 停摆 8h 无告警）
      printf 'dispatch 停摆：连续 %s 轮 exit 2（自 %s）；见 locks/dispatch.log 尾部与环境自检\n' "$n" "$(ts)" > "$STALLED_MARK"
      printf '环境自检: core.bare=%s git-toplevel=%s worktrees=%s\n' \
        "$(git -C "$REPO" config core.bare 2>/dev/null || echo '?')" \
        "$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null || echo FAIL)" \
        "$(git -C "$REPO" worktree list 2>/dev/null | wc -l | tr -d ' ')" >> "$STALLED_MARK"
      /usr/bin/osascript -e "display notification \"dispatch 连续 ${n} 轮 exit=2（环境自检见 ${METRICS}/dispatch-stalled）\" with title \"factory 工厂停摆（${REPO##*/}）\"" >/dev/null 2>&1 || true
      # 即时飞书（2026-09-01 用户要求"第一时间"）：stalled 无法自愈需人工介入，
      # 聚合层（dispatch-all.sh）注入 ALERT_CMD/ALERT_OPEN_ID/ALERT_SENT_DIR 时
      # 立即推送；指纹与聚合层共享（alerts/sent/<repo>.stalled），30min tick
      # 不重复推，恢复后由聚合层 clear_alerts 清除。
      if [ -n "${ALERT_CMD:-}" ] && [ -n "${ALERT_OPEN_ID:-}" ] && [ -x "$ALERT_CMD" ]; then
        fp="${ALERT_SENT_DIR:+${ALERT_SENT_DIR}/${REPO##*/}.stalled}"
        if [ -z "$fp" ] || [ ! -f "$fp" ]; then
          if python3 "$ALERT_CMD" "$ALERT_OPEN_ID" "[factory] ${REPO##*/} dispatch 停摆（exit=2 连击 ${n} 轮）——无法自愈需人工介入；环境自检见 ${STALLED_MARK}" >/dev/null 2>&1; then
            [ -n "$fp" ] && { mkdir -p "$ALERT_SENT_DIR"; touch "$fp"; }
            echo "  即时飞书已推送"
          else
            echo "  即时飞书推送失败（不标记，聚合层下轮重试）"
          fi
        fi
      fi
    fi
  elif [ "$drc" -eq 0 ]; then
    rm -f "$STREAK" "$STALLED_MARK"
  fi
} >> "${LOG}" 2>&1
