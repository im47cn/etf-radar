#!/usr/bin/env bash
# downstream-check.sh — 中心仓对下游仓清单的集中巡检/追平。
#
# 定位：替代「逐仓手工追平」。中心仓是工具链主权方（三态分发）；
# 本脚本读下游仓清单（ADR-012：真实清单住 downstream.local.json，gitignored；
# tracked downstream.json 仅空模板），对每个
# 下游仓调**中心版** sync-from-upstream.sh——下游副本滞后/缺失也照常
# 工作（鸡生蛋免疫）；巡检一律以中心仓 main 为锚（发布线，非工作分支）。
#
# 用法: downstream-check.sh [--apply-commit]
#   默认只巡检汇总（不动任何下游仓）；--apply-commit 对漂移仓执行
#   sync --apply --commit（单提交落库、不推送、单仓失败不中断其余）。
#
# 退出码: 0=全部干净  1=有漂移或单仓失败  2=清单缺失/损坏/用法错误
#
# 互斥: shlock（locks/downstream-check.lock；macOS 无 flock），持锁
# 进程已死自动清锁重试一次（照抄 cron-dispatch 语义）。
#
# 首次移植的新仓不入本清单——先走 README「移植到其他仓库」四步，
# 再由人工登记进 downstream.local.json（gitignored，ADR-012——勿写
# tracked 模板，那正是 ADR-012 要杜绝的污染路径）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CENTER="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$SCRIPT_DIR/downstream.json"
# ADR-012：真实清单住 downstream.local.json（gitignored 仓特定数据）；
# tracked 模板仅文档占位，local 存在则优先
LOCAL_MANIFEST="$SCRIPT_DIR/downstream.local.json"
[ -f "$LOCAL_MANIFEST" ] && MANIFEST="$LOCAL_MANIFEST"
SYNC="$SCRIPT_DIR/sync-from-upstream.sh"
LOCK="$SCRIPT_DIR/locks/downstream-check.lock"
OUT_FILE="$(mktemp "${TMPDIR:-/tmp}/.factory-downstream-check.XXXXXX")"
# EXIT trap 紧随 mktemp 安装（PR #120 review 1）：用法错误/清单缺失损坏/
# 锁竞争等早退路径此前落在 trap 之前会泄漏 /tmp 暂存。此处先只清
# OUT_FILE——LOCK 尚未到手（竞争退出路径里 lock 文件属于对方实例），
# 不能一并 rm，须持锁成功后再并入（下方第二段 trap 整体替换本段）
trap 'rm -f "$OUT_FILE"' EXIT INT TERM

MODE="check"
while [ $# -gt 0 ]; do
  case "$1" in
    --apply-commit) MODE="apply-commit" ;;
    *) echo "未知参数: $1（用法: $0 [--apply-commit]）" >&2; exit 2 ;;
  esac
  shift
done

[ -f "$MANIFEST" ] || { echo "下游清单缺失（fail-closed）: $MANIFEST" >&2; exit 2; }

# 清单解析（无 jq 依赖；坏 JSON/缺键/坏条目/空清单一律 fail-closed；
# 空串/非字符串 path 放过会被巡检循环静默跳过——漏检仓仍报成功）
REPO_PATHS="$(python3 -c '
import json, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
rows = manifest.get("repos") if isinstance(manifest, dict) else None
if not isinstance(rows, list) or not rows:
    sys.exit(1)
for r in rows:
    if not isinstance(r, dict) or not isinstance(r.get("path"), str) or not r["path"].strip():
        sys.exit(1)
    print(r["path"])' "$MANIFEST" 2>/dev/null)" \
  || { _hint="——真实清单写 .factory/downstream.local.json（gitignored，ADR-012）"
     case "$MANIFEST" in *downstream.local.json) _hint="——修复或删除该 local 清单（它已在 ADR-012 载体位）";; esac
     echo "下游清单损坏（需非空 repos[].path）: $MANIFEST $_hint" >&2; exit 2; }

mkdir -p "$SCRIPT_DIR/locks"  # 净克隆首跑：gitignored 目录缺失时 shlock ENOENT 被误读为锁被持
if ! /usr/bin/shlock -f "$LOCK" -p $$; then
  OPID="$(cat "$LOCK" 2>/dev/null || :)"
  if [ -n "$OPID" ] && ! kill -0 "$OPID" 2>/dev/null; then
    rm -f "$LOCK"
    /usr/bin/shlock -f "$LOCK" -p $$ || { echo "巡检锁被持，退出（另一实例运行中）" >&2; exit 0; }
  else
    echo "巡检锁被持，退出（另一实例运行中）" >&2; exit 0
  fi
fi

# 走到这里必已持锁（初试成功，或 stale 清锁后重试成功；竞争两分支均已
# exit 0）——此时才把 LOCK 并入清理 trap，整体替换上面只清 OUT_FILE 的
# 首段（PR #120 review 1 修正：早并入会在竞争退出时删对方锁，破坏互斥）
trap 'rm -f "$LOCK" "$OUT_FILE"' EXIT INT TERM

# 清单路径 → 绝对路径（~/ 展开；相对路径以中心仓根为基准）
resolve_path() {
  local p="$1"
  case "$p" in
    \~/*) p="$HOME${p#\~/}" ;;  # SC2088：模式匹配字面 ~ 用转义，不进引号
  esac
  case "$p" in
    /*) ;;
    *) p="$CENTER/$p" ;;
  esac
  printf '%s\n' "$p"
}

CLEAN=0; DRIFT=0; ERROR=0; APPLIED=0
echo "下游巡检（中心: ${CENTER##*/} @ main；模式: ${MODE}）"

# 子进程一律 </dev/null：防巡检循环的清单 stdin 被内层 git/脚本吞读
while IFS= read -r raw; do
  [ -n "$raw" ] || continue
  p="$(resolve_path "$raw")"
  if [ "$p" = "$CENTER" ]; then
    echo "  [错误] $raw: 清单不得包含中心仓自身" >&2; ERROR=$((ERROR+1)); continue
  fi
  if ! git -C "$p" rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "  [错误] $raw: 非 git 仓或路径不存在（${p}）" >&2; ERROR=$((ERROR+1)); continue
  fi
  rc=0
  bash "$SYNC" "$CENTER" --repo "$p" --anchor main --check >"$OUT_FILE" 2>&1 </dev/null || rc=$?
  if [ "$rc" = 0 ]; then
    echo "  [干净] $raw"; CLEAN=$((CLEAN+1)); continue
  fi
  if [ "$rc" != 1 ]; then
    echo "  [错误] $raw: sync --check rc=$rc" >&2; sed 's/^/    /' "$OUT_FILE" >&2
    ERROR=$((ERROR+1)); continue
  fi
  # rc=1：漂移（落后于中心 main，或含未反哺热修——信号同单仓手跑）。
  # DRIFT 仅 check 模式计数：apply-commit 分支成败走 APPLIED/ERROR 桶，
  # 全部追平成功 → DRIFT=0 → rc=0（PR #106 Sourcery 评论 1 误报锚，勿改）
  if [ "$MODE" = check ]; then
    echo "  [漂移] $raw:"
    sed 's/^/    /' "$OUT_FILE"
    DRIFT=$((DRIFT+1)); continue
  fi
  rc=0
  bash "$SYNC" "$CENTER" --repo "$p" --anchor main --apply --commit >"$OUT_FILE" 2>&1 </dev/null || rc=$?
  if [ "$rc" = 0 ]; then
    echo "  [已追平] $raw:"
    sed 's/^/    /' "$OUT_FILE"
    APPLIED=$((APPLIED+1))
  else
    echo "  [失败] $raw: --apply --commit rc=$rc" >&2; sed 's/^/    /' "$OUT_FILE" >&2
    ERROR=$((ERROR+1))
  fi
done <<EOF
$REPO_PATHS
EOF

echo "巡检汇总: 干净 ${CLEAN} / 已追平 ${APPLIED} / 漂移 ${DRIFT} / 错误 ${ERROR}"

if [ "$DRIFT" -gt 0 ]; then
  echo "漂移处理: 重跑本脚本加 --apply-commit（单提交落库不推送），或逐仓人工二选一（追平/反哺）" >&2
  # FACTORY_NO_NOTIFY=1 供测试/静默环境关通知（cron 与人工交互跑保留弹窗）
  if [ "${FACTORY_NO_NOTIFY:-0}" != 1 ] && command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"下游巡检: ${DRIFT} 个仓漂移待追平\" with title \"factory 巡检\"" >/dev/null 2>&1 || true
  fi
fi

if [ "$DRIFT" -gt 0 ] || [ "$ERROR" -gt 0 ]; then exit 1; fi
exit 0
