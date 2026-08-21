#!/bin/sh
# cron 包装器：cron 环境无 PATH/git/gh/omp —— 在此显式注入。
# 互斥：macOS 无 flock，用原生 shlock（.factory/locks/dispatch.lock）。
# 日志固定尾追 .factory/locks/dispatch.log（gitignored）。
set -u
SELF=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
REPO=$(CDPATH='' cd -- "$(dirname -- "$SELF")/.." && pwd)
LOG="${REPO}/.factory/locks/dispatch.log"
LOCK="${REPO}/.factory/locks/dispatch.lock"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$REPO" || { echo "无法进入 ${REPO}" >&2; exit 2; }
export PATH HOME="${HOME:?cron 环境未设置 HOME}"
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
  echo "── $(ts) triage 批次开始"
  "${REPO}/.factory/triage-batch.sh" && rc=0 || rc=$?
  echo "── $(ts) triage 批次结束（exit=${rc}）"
  echo "── $(ts) dispatch 开始"
  "${REPO}/.factory/dispatch.sh"
  echo "── $(ts) dispatch 结束（exit=$?）"
} >> "${LOG}" 2>&1
