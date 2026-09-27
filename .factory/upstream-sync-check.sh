#!/usr/bin/env bash
# upstream-sync-check.sh — M2：工厂机制自动消费上游修复（设计 §11.2）。
#
# 不复用 fix-issue 链：guard PERIMETER 含 .factory/（质检线纪律），链内
# 工具链改动必被周界门拦下——工具链自变更走本确定性 PR 流（机器执行、
# 人类合并），与 validate-pr 同构。全程零 LLM 节点，不占 R4 熔断预算。
#
# 用法: upstream-sync-check.sh [--dry-run]
# 分诊（确定性，无 LLM）:
#   full 漂移  → apply → gauntlet → factory/sync-<锚点短SHA> 分支 push
#                → gh pr create（factory:needs-review）→ 人工合并
#   local 漂移 → gh issue create 落 needs-human（local 面是语义决策，
#                不可自动合并——判据 c 周界语义在同步面的投影）
#   无漂移     → 静默退出 0
#
# 护栏（设计 §11.2 第 4 条）:
#   - 幂等：PR head 分支名含锚点 SHA，同锚点重跑 push 同分支（PR 自动
#     更新），不叠加 PR
#   - fail-closed：gauntlet 红不 push，漂移保留人工介入（退出码 1）
#   - 凭据探测：gh auth 不可用（无凭据环境）→ 降级为本地报告 + exit 3，
#     由调用方（dispatch）决定落 issue 或仅记日志——降级不产生任何
#     远端副作用
#   - 自我指涉由调用方处理：apply 后 dispatch 当轮即止（本脚本退出码 0
#     即「已应用」，dispatch 见 0 即停本轮后续派发）
#
# 退出码: 0 = 无漂移或 PR 已开（同步已推进，调用方当轮即止）
#         1 = 漂移存在但推进失败（gauntlet 红/分支推失败）→ 人工介入
#         2 = 用法/上游不可用/锁文件缺 upstream 字段
#         3 = 无凭据降级（本地已报告，无远端副作用）
set -euo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

REPO="$(git rev-parse --show-toplevel)"
FACTORY="$REPO/.factory"
HOST="python3 ${FACTORY}/hosting.py"
LOCK="$FACTORY/upstream-lock.json"

# 上游路径：锁文件 upstream 字段（M2 约定）> 环境变量 > 退出 2
UP="$(python3 -c '
import json, sys
try: print(json.loads(open(sys.argv[1]).read())["upstream"])
except Exception: pass' "$LOCK" 2>/dev/null || true)"
UP="${FACTORY_UPSTREAM:-${UP:-}}"
[ -n "$UP" ] || { echo "upstream-sync: upstream-lock.json 缺 upstream 字段且未设 FACTORY_UPSTREAM" >&2; exit 2; }

# 凭据探测：无凭据环境降级（设计约束：降级不产生远端副作用）
if ! ${HOST} auth ok >/dev/null 2>&1; then
  echo "upstream-sync: 无托管平台凭据（降级模式）——本地漂移报告：" >&2
  bash "$FACTORY/sync-from-upstream.sh" "$UP" --check 2>&1 | sed 's/^/  /' >&2 || true
  echo "upstream-sync: 人工追平: $FACTORY/sync-from-upstream.sh $UP --apply" >&2
  exit 3
fi

# 漂移检查：--check exit 1 = full 面有漂移；local 面仅报告（stdout 摘要）。
# rc=0 干净；rc=1 漂移；rc=2+（用法/上游不可用/锚点不可解析）是致命失败——
# 输出不带 [local]/[full] 标记，落入下方分支会被当「无漂移」吞掉而 exit 0，
# 调用方把致命检查失败误判为干净（Sourcery PR#14 评论 1）→ 必须原样上抛
CHECK_RC=0
CHECK_OUT="$(bash "$FACTORY/sync-from-upstream.sh" "$UP" --check 2>&1)" || CHECK_RC=$?
if [ "$CHECK_RC" -eq 0 ]; then
  echo "$CHECK_OUT" | grep -q 'local.*人工\|漂移' || true
  echo "upstream-sync: full 面干净，无动作"
  exit 0
fi
if [ "$CHECK_RC" -ge 2 ]; then
  echo "$CHECK_OUT" >&2
  exit "$CHECK_RC"
fi

echo "$CHECK_OUT"
# local 漂移落 needs-human issue（零 LLM 分诊：语义决策归人类）
if echo "$CHECK_OUT" | grep -q '\[local\].*差'; then
  LOCAL_SUMMARY="$(echo "$CHECK_OUT" | grep '\[local\].*差' | head -20)"
  if [ "$DRY" = 0 ]; then
    ${HOST} issue create --title "factory 上游 local 面漂移（人工合并）" \
      --label factory:needs-human --body "上游 \`${UP}\` 与本仓 local 面文件存在分叉——local 含仓特定区，不可自动合并（设计 §11.2 分诊）。

正道：对上游修通用缺陷 → feedback-upstream.sh 反哺 PR → 上游合并 → 本仓 --apply 追平。

${LOCAL_SUMMARY}

## 验收（可机械判定）

- [ ] \`bash .factory/sync-from-upstream.sh ${UP} --check\` 不再报 [local] 分叉，或本 issue 下留有人工合并决策评论" \
      && echo "upstream-sync: local 漂移已落 needs-human issue" \
      || echo "upstream-sync: issue 创建失败（继续 full 面处理）" >&2
  else
    echo "[dry-run] 将创建 local 漂移 issue: ${LOCAL_SUMMARY}"
  fi
fi

# full 漂移 → 确定性 PR 流
if echo "$CHECK_OUT" | grep -q '\[full\].*漂移\|\[full\].*缺失'; then
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] full 漂移存在，将走确定性 PR 流（apply → gauntlet → PR）"
    exit 1
  fi
  bash "$FACTORY/sync-from-upstream.sh" "$UP" --apply
  echo "-- gauntlet（同步后全量门禁）--"
  if ! bash tools/gauntlet.sh; then
    echo "upstream-sync: gauntlet 红门——不 push，漂移保留人工介入（fail-closed）" >&2
    exit 1
  fi
  ANCHOR="$(python3 -c '
import json, sys
print(json.loads(open(sys.argv[1]).read())["anchor"][:9])' "$LOCK")"
  BR="factory/sync-${ANCHOR}"
  git add .factory
  if git diff --cached --quiet; then
    echo "upstream-sync: apply 后无待提交变更（内容已等价）"
    exit 0
  fi
  git commit -qm "chore(factory): 上游同步追平 ${ANCHOR}（M2 确定性 PR 流）"
  git push -q --no-verify origin "HEAD:refs/heads/${BR}"
  # base 显式（PR #116）：同步基点为 main（factory-lock 锚点语义），不猜默认
  PR_URL="$(${HOST} pr create --head "$BR" --title "factory: 上游同步追平（${ANCHOR}）" \
    --base "${FACTORY_BASE_BRANCH:-main}" \
    --label factory:needs-review \
    --body "M2 确定性 PR 流（设计 §11.2）：full 面漂移自动追平，机器执行、人工合并。

- 锚点: \`${ANCHOR}\`
- gauntlet 全量门禁已过（fail-closed：红门不 push）
- 同锚点重跑幂等（push 同分支，PR 自动更新）" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("url") or "")')" \
    || PR_URL="(PR 已存在或创建失败——分支 ${BR} 已推送，可手工开 PR)"
  echo "upstream-sync: 同步 PR ${PR_URL}（人工合并）"
  exit 0
fi

# 只有 local 漂移（无 full）：不建同步分支
echo "upstream-sync: 仅 local 面漂移——已落 issue，无 full 动作"
exit 0
