#!/usr/bin/env bash
# triage 批次: 每轮对无任何 factory:* 标签的 open issue 跑物理隔离 triage 裁决。
# 补齐 S2 缺口: "写 issue → 工厂自动看见"——裁决落标后自然流入 dispatch 队列。
#
# 铁律 4 边界(有意设计): 本脚本作为调度是纯 bash + gh 读标签(无标签=待裁决);
# accept/reject 由 triage 节点按 MISSION 裁决, LLM 不参与调度决策。
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
REPO_SLUG="${GH_REPO:-$(
  # 双 remote 布局：origin pushurl 可能多条（codeup 镜像 + github），
  # 逐条扫含 github.com 者（github remote 名优先）；443 端口形态兼容
  { git -C "$REPO" remote get-url --all --push github 2>/dev/null
    git -C "$REPO" remote get-url --all --push origin 2>/dev/null
  } | grep -m1 'github\.com' | sed -E 's#^.*github\.com(:[0-9]+)?[/:]##; s#\.git$##'
)}"
[ -n "$REPO_SLUG" ] || { echo "无法确定 GitHub 仓库 slug" >&2; exit 2; }
MAX_TRIAGE="${MAX_TRIAGE:-5}"
command -v gh >/dev/null || { echo "需要 gh CLI" >&2; exit 2; }
# 链副作用共享库（契约：REPO/REPO_SLUG 已定义；ISSUE 为循环变量）
source "${FACTORY}/factory-lib.sh"

# 零 factory 标签的 open issue（json 一次取齐, python 过滤排序）
QUEUE="$(gh issue list --repo "$REPO_SLUG" --state open --limit 100 \
  --json number,labels,title,body,comments \
  | python3 -c '
import json, sys
for i in json.load(sys.stdin):
    if not any(l["name"].startswith("factory:") for l in i["labels"]):
        print(i["number"])')"

COUNT=0
for ISSUE in $QUEUE; do
  COUNT=$((COUNT+1)); [ "$COUNT" -gt "$MAX_TRIAGE" ] && { echo "达每轮上限 $MAX_TRIAGE, 余量下轮"; break; }
  DIR="${FACTORY}/artifacts/issue-${ISSUE}"
  mkdir -p "$DIR"
  gh issue view "${ISSUE}" --repo "$REPO_SLUG" --json number,title,body,comments > "${DIR}/issue.json"

  mission="$(cat "${REPO}/MISSION.md")"
  title="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["title"])' "${DIR}/issue.json")"
  body="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("body") or "")' "${DIR}/issue.json")"
  cmts="$(python3 - "${DIR}/issue.json" <<'PYC'
import json, sys
d = json.load(open(sys.argv[1]))
cs = d.get("comments") or []
out = "\n\n".join("[作者: %s]\n%s" % (c["author"]["login"], c["body"]) for c in cs[-3:])
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
  if ! (cd "$REPO" && omp -p "$prompt" --no-tools --no-session --max-time 5m < /dev/null) \
      > "${DIR}/triage.log" 2>&1; then
    echo "    triage 节点失败（详见 ${DIR}/triage.log）, 跳过" >&2; continue
  fi
  if ! python3 "${FACTORY}/factory_lib.py" parse "${DIR}/triage.log" "${DIR}/triage.json" accept,reject; then
    echo "    triage 输出无法解析, 跳过" >&2; continue
  fi
  VERDICT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "${DIR}/triage.json")"
  if [ "$VERDICT" = accept ]; then
    gh issue edit "${ISSUE}" --repo "$REPO_SLUG" --add-label factory:accepted >/dev/null
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
