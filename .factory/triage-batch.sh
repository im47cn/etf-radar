#!/usr/bin/env bash
# triage 批次: 每轮对无任何 factory:* 标签的 open issue 跑物理隔离 triage 裁决。
# 补齐 S2 缺口: "写 issue → 工厂自动看见"——裁决落标后自然流入 dispatch 队列。
#
# 铁律 4 边界(有意设计): 本脚本作为调度是纯 bash + hosting 读标签
# (无标签=待裁决; ADR-008 起 gh 由 hosting.py 收口); accept/reject 由
# triage 节点按 MISSION 裁决, LLM 不参与调度决策。
# 与 S1 链的竞态窗口: 链启动即打 factory:triaging, 本批次只挑零标签 issue,
# 秒级窗口可忽略。
#
# 限量: 每轮 MAX_TRIAGE(默认 5)个, 防标签批量清理后的重裁风暴。
# 产物: .factory/artifacts/issue-N/triage.{json,log}（fix-issue 链复用重裁, 幂等）
# reject 落标+判据回执经 factory-lib.sh issue_reject() 单一动作收口
# （#59 二次拒绝静默实证：批次只落标不发回执 = 链路缺陷的另一半）
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
FACTORY="$REPO/.factory"
HOST="python3 ${FACTORY}/hosting.py"
MAX_TRIAGE="${MAX_TRIAGE:-5}"
${HOST} auth ok >/dev/null 2>&1 || { echo "Hosting platform unavailable (hosting auth)" >&2; exit 2; }
# 链副作用共享库（契约：REPO/ISSUE 已定义；ADR-008 起 REPO_SLUG 不再需要）
source "${FACTORY}/factory-lib.sh"
# --- R4 成本熔断：批次是 LLM 成本入口之一（手动直跑路径此前无门，
# 2026-08-24 收口）。透传 breaker 码：3=熔断 / 1=门故障 fail-closed，
# set -e 下均直接停摆，明细见 breaker.sh stderr。---
if [ "${DRY:-0}" = 0 ]; then
  bash "${FACTORY}/breaker.sh" "${FACTORY}/locks"
fi

# 零 factory 标签的 open issue（中立 JSON 一次取齐, python 过滤排序）。
# 平台瞬断（2026-08-23 实证形态）时给出可读降级信息退出 rc=1，而非
# json.load 裸 traceback——批次失败由上游容忍（cron 下一 tick 重试），
# 但错误形态必须可诊断。
QUEUE="$(${HOST} issue list --state open --limit 100 --comments 2>/dev/null \
  | python3 -c '
import json, sys
try:
    issues = json.loads(sys.stdin.read())
except ValueError:
    issues = None
if not isinstance(issues, list):
    sys.stderr.write("triage 批次: hosting issue list 输出非 JSON（平台失败/网络瞬断），本轮跳过\n")
    sys.exit(1)
for i in issues:
    if not any(l.startswith("factory:") for l in i["labels"]):
        print(i["number"])' )" || exit 1

COUNT=0
for ISSUE in $QUEUE; do
  COUNT=$((COUNT+1)); [ "$COUNT" -gt "$MAX_TRIAGE" ] && { echo "达每轮上限 $MAX_TRIAGE, 余量下轮"; break; }
  DIR="${FACTORY}/artifacts/issue-${ISSUE}"
  mkdir -p "$DIR"
  if ! ${HOST} issue view "${ISSUE}" > "${DIR}/issue.json"; then
    echo "    issue #${ISSUE} 取回失败（平台失败/网络瞬断），跳过" >&2; continue
  fi

  mission="$(cat "${REPO}/MISSION.md")"
  title="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["title"])' "${DIR}/issue.json")"
  body="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("body") or "")' "${DIR}/issue.json")"
  cmts="$(python3 - "${DIR}/issue.json" <<'PYC'
import json, sys
d = json.load(open(sys.argv[1]))
cs = d.get("comments") or []
out = "\n\n".join("[作者: %s]\n%s" % (c.get("author") or "?", c["body"]) for c in cs[-3:])
print(out if out else "（无评论）")
PYC
)"
  prompt="$(cat "${FACTORY}/prompts/triage.md")

——MISSION.md 开始——
${mission}
——MISSION.md 结束——

——issue #${ISSUE} 标题: ${title} 正文开始——
${body}
——正文结束——

——issue 评论开始（最新 3 条）——
${cmts}
——评论结束——"

  echo "==> triage #${ISSUE}: ${title}"
  if ! omp_node "$REPO" "${DIR}/triage.log" 5m --no-tools -- "$prompt"; then
    echo "    triage 节点失败（详见 ${DIR}/triage.log）, 跳过" >&2; continue
  fi
  if ! python3 "${FACTORY}/factory_lib.py" parse "${DIR}/triage.log" "${DIR}/triage.json" accept,reject; then
    echo "    triage 输出无法解析, 跳过" >&2; continue
  fi
  VERDICT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "${DIR}/triage.json")"
  if [ "$VERDICT" = accept ]; then
    issue_label_swap "" "factory:accepted"   # 收口出口（ADR-008 层级契约）：与 reject 同一标签转移通道
    echo "    → accept（已入派发队列）"
  else
    # 落标 + 判据回执一次收口；落标失败仅告警不中断批次（下一 issue 继续）
    if issue_reject "" "${DIR}/triage.json"; then
      echo "    → reject（人工补充上下文后移除标签即可重裁）"
    else
      echo "    [warn] 拒绝落标失败（issue #${ISSUE}），跳过回执" >&2
    fi
  fi
done
[ "$COUNT" -eq 0 ] && echo "无待裁决 issue（零 factory 标签）" || true
