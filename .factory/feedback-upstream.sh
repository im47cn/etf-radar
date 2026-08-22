#!/usr/bin/env bash
# feedback-upstream.sh — 反哺上游：etf-radar 工厂改进 → awesome-rules PR。
#
# 定位：人工治理工具（dispatch/链永不调用；铁律 4 不受影响——本脚本不是
# dispatcher）。决策零 LLM：bash/git/gh 决定开不开 PR；omp 适配节点只产出
# 内容（clean cherry-pick 由脚本完成保持保真，AI 仅处理冲突与特化剥离），
# 与链同构：AI 产出、确定性门（上游 scripts/run_tests.sh）做决策、人合并。
#
# 用法: feedback-upstream.sh [--dry-run]
#   --dry-run  只打印待反哺候选与上游漂移报告，零副作用
# env: UPSTREAM_PATH(默认 ~/sources/awesome-rules)  UPSTREAM_REPO(默认 im47cn/awesome-rules)
#      NODE_TIMEOUT(适配节点预算，默认 30m)
set -euo pipefail

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "不在仓库内" >&2; exit 2; }
FACTORY="$REPO/.factory"
UPSTREAM_PATH="${UPSTREAM_PATH:-$HOME/sources/awesome-rules}"
UPSTREAM_REPO="${UPSTREAM_REPO:-im47cn/awesome-rules}"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

say() { printf '%s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }

# --- 1. 待反哺候选（trailer ∨ bootstrap，− 账本；旧→新） ---
PENDING="$(python3 "$FACTORY/feedback.py" pending)" || die "候选收集失败"
[ -z "$PENDING" ] && { say "无待反哺候选（账本已覆盖全部标记提交）"; exit 0; }
N_TOTAL="$(printf '%s\n' "$PENDING" | wc -l | tr -d ' ')"
say "待反哺候选: ${N_TOTAL} 个"

# --- 2. 上游可用性（2026-08-22 起上游为 bare 仓，无 .git 子目录与工作树） ---
git -C "$UPSTREAM_PATH" rev-parse --git-dir >/dev/null 2>&1 \
  || die "上游仓不可用: $UPSTREAM_PATH"


# --- 3. 上游准备：独立 worktree（不碰上游主工作区及其未提交改动，同链 D3 实践） ---
STAMP="$(date +%Y%m%d-%H%M%S)"
FB_DIR="$FACTORY/artifacts/feedback-$STAMP"
mkdir -p "$FB_DIR/patches"
BRANCH="feedback/etf-radar-$(date +%Y%m%d)"
# 目录名与断言解耦：上游 repo_root 测试已改锚结构不变量（PR #22），
# checkout 目录名不再参与判定；保留 basename 仅为语义可读
WT="$FB_DIR/upstream-wt/awesome-rules"
mkdir -p "$FB_DIR/upstream-wt"
GITUP=(git -C "$UPSTREAM_PATH")
# remote 拓扑随用户工作流变化（2026-08-22 实测：github remote 并入 origin 双推送，
# fetch=codeup 镜像 / push=codeup+github）。故不假设 remote 名：
# - 拉基点用 origin（用户既定事实源；有专用 fetch remote 时优先）
# - 推送显式解析 github push-URL 直推，避免多 pushurl 连带镜像
FREMOTE="$("${GITUP[@]}" remote -v | awk -v repo="$UPSTREAM_REPO" \
  '$0 ~ repo && $3 == "(fetch)" {print $1; exit}')"
FREMOTE="${FREMOTE:-origin}"
"${GITUP[@]}" fetch "$FREMOTE" main --quiet
BASE="$("${GITUP[@]}" rev-parse --verify "$FREMOTE/main^{commit}")" \
  || die "无法解析 $FREMOTE/main"
PUSH_URL="$("${GITUP[@]}" remote -v | awk -v repo="$UPSTREAM_REPO" \
  '$0 ~ /github\.com/ && $0 ~ repo && $3 == "(push)" {print $2; exit}')"
[ -n "$PUSH_URL" ] || die "上游 clone 无指向 github.com/${UPSTREAM_REPO} 的 push url"
# 跨仓对象：上游对象库没有本仓提交，cherry-pick 前临时挂源 remote 拉取
# （结束移除；拉入对象随后不可达，交由上游 gc，无残留引用）
REMOTE_ADDED=0
if "${GITUP[@]}" remote add feedback-src "$REPO" >/dev/null 2>&1; then
  REMOTE_ADDED=1
else
  # 已存在则验证可用后复用；仅本次添加的才在 cleanup 移除（防误删用户既有 remote）
  "${GITUP[@]}" remote get-url feedback-src >/dev/null 2>&1 \
    || die "feedback-src remote 已存在但不可用"
fi
"${GITUP[@]}" fetch -q feedback-src main
cleanup() {
  git -C "$UPSTREAM_PATH" worktree remove --force "$WT" >/dev/null 2>&1 || true
  git -C "$UPSTREAM_PATH" branch -qD "$BRANCH" >/dev/null 2>&1 || true
  # 仅移除本次添加的 remote；已存在被复用的不动（防误删用户既有配置）
  [ "$REMOTE_ADDED" = 1 ] \
    && git -C "$UPSTREAM_PATH" remote remove feedback-src >/dev/null 2>&1 || true
}
trap cleanup EXIT
abandon() { say "已放弃，分支与 worktree 已清理（产物: ${FB_DIR}）"; exit 1; }
"${GITUP[@]}" worktree add -q -B "$BRANCH" "$WT" "$BASE" \
  || die "worktree 创建失败（分支 $BRANCH 可能被占用，请手工清理）"
GITW=(git -C "$WT")
say "上游 worktree: $WT 分支: $BRANCH (基点 $FREMOTE/main@${BASE:0:9})"

# --- 3.5 漂移报告（上游独有/两侧分歧，仅报告不动作；对 worktree 检出内容，
#     上游 bare 无工作树，2026-08-22 前的磁盘直比已不可行） ---
python3 "$FACTORY/feedback.py" report "$WT"
[ "$DRY" = 1 ] && { say "[dry-run] 到此为止，未做任何变更"; exit 0; }

# --- 3.6 依赖闭包（fail-closed）：候选脚本引用的 .factory 资产必须
#     上游已有 ∨ 候选随行；防 PR #18 只带主脚本、配套件断链复演 ---
python3 "$FACTORY/feedback.py" closure "$WT"

# --- 4. cherry-pick：clean 保真，conflicted 交适配节点 ---
CONFLICTED=()
while IFS=$'\t' read -r sha subject; do
  if "${GITW[@]}" cherry-pick "$sha" >/dev/null 2>&1; then
    say "  pick  ${sha:0:9}  $subject"
  else
    "${GITW[@]}" cherry-pick --abort >/dev/null 2>&1 || true
    CONFLICTED+=("$sha")
    say "  冲突  ${sha:0:9}  $subject → 适配节点"
  fi
done <<< "$PENDING"

# --- 5. 适配节点（必跑：clean 候选也需审查特化剥离） ---

python3 - "$FB_DIR" "$PENDING" ${CONFLICTED[@]+"${CONFLICTED[@]}"} <<'PYEOF'
import json, pathlib, subprocess, sys
fb_dir, pending, conflicted = sys.argv[1], sys.argv[2], sys.argv[3:]
conflicted = set(conflicted)
items = []
for line in pending.splitlines():
    sha, subject = line.split("\t", 1)
    patch = pathlib.Path(fb_dir) / "patches" / ("%s.patch" % sha[:9])
    patch.write_text(subprocess.run(
        ["git", "show", "--format=fuller", sha],
        capture_output=True, text=True, check=True).stdout, encoding="utf-8")
    items.append({"sha": sha, "subject": subject, "status":
                  "conflicted" if sha in conflicted else "clean",
                  "patch": str(patch.relative_to(fb_dir))})
pathlib.Path(fb_dir, "manifest.json").write_text(
    json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
PROMPT="$(cat "$FACTORY/prompts/feedback-adapt.md")

——任务参数:
- FEEDBACK_DIR: $FB_DIR
- 上游 worktree: ${WT}（你在此工作树上操作；基点含上游最新 main）
- 候选数: ${N_TOTAL}（manifest.json 为准）"
say "==> 适配节点（fresh context 进程，预算 ${NODE_TIMEOUT:-30m}）"
NODE_RC=0
(cd "$WT" && omp -p "$PROMPT" --no-session \
      --max-time "${NODE_TIMEOUT:-30m}" </dev/null) > "$FB_DIR/adapt.log" 2>&1 || NODE_RC=$?
ART_PATH="$(sed -n 's/^ARTIFACT: //p' "$FB_DIR/adapt.log" | tail -1)"

# --- 6. 确定性验证（不信任节点自觉）：产物 / 提交数 / 周界 / 干净树 ---
# omp --no-session 偶发非零退出码但工作完成（2026-08-22 实测），退出码只降级为警告；
# 真正的验收是 ARTIFACT 存在 + 以下确定性检查 + 第 7 节上游门禁
if [ -z "$ART_PATH" ] || [ ! -f "$ART_PATH" ]; then
  abandon
  die "适配节点未产出 ARTIFACT（日志: ${FB_DIR}/adapt.log）"
fi
[ "$NODE_RC" = 0 ] || say "⚠ 适配节点退出码 ${NODE_RC}（工作已完成，以下确定性检查为准）"
N_COMMITS="$("${GITW[@]}" rev-list --count "$BASE..HEAD")"
if [ "$N_COMMITS" != "$N_TOTAL" ]; then
  abandon
  die "提交数 ${N_COMMITS} ≠ 候选数 ${N_TOTAL}（一候选一提交契约破坏）"
fi
BAD_FILES="$("${GITW[@]}" diff --name-only "$BASE..HEAD" | grep -v '^\.factory/' || true)"
if [ -n "$BAD_FILES" ]; then
  abandon
  die "越界改动（仅允许 .factory/）: $(echo "$BAD_FILES" | tr '\n' ' ')"
fi
[ -z "$("${GITW[@]}" status --porcelain)" ] || die "上游 worktree 残留未提交改动（adapt.md 说明见 ${FB_DIR}）"
say "✓ 适配完成: ${N_COMMITS} commits，全部位于 .factory/"

# --- 7. 上游门禁：红 → 不开 PR，只收报告 ---
# gauntlet（不是 run_tests.sh）: 2026-08-22 事故——适配节点产出 BRANCH 未定义
# （SC2154）的 fix-issue.sh 逃过纯 pytest 门禁; gauntlet 的 .factory shell 三层
# （syntax/lint -S warning/inline-python）正是为该逃逸所补。pytest 层两者等价。
say "==> 上游门禁: tools/gauntlet.sh"
if (cd "$WT" && sh tools/gauntlet.sh) \
    > "$FB_DIR/gate.log" 2>&1; then
  say "✓ 上游门禁绿（$FB_DIR/gate.log）"
else
  abandon
  die "上游门禁红，未开 PR（报告: $FB_DIR/gate.log）"
fi


# --- 8. PR：推送 + gh 显式 --repo/--head（上游 origin 非 github 的坑已修） ---
# --no-verify：git 注入 GIT_DIR 使 pre-push 全量套件在污染 env 下假红
# （skills/* 测试非密封，2026-08-22 实测 tmp_path 内 git init 被劫持）；
# 门禁主权归第 7 节脚本确定性执行
"${GITW[@]}" push -q --no-verify "$PUSH_URL" "$BRANCH"
PR_BODY="$FB_DIR/pr-body.md"
{ echo "自 etf-radar 反哺工厂改进（一候选一提交，clean pick 保真 / conflicted 适配）。"
  echo
  printf '%s\n' "$PENDING" | while IFS=$'\t' read -r sha subject; do
    echo "${sha:0:9}  $subject"
  done
  echo '```'
  echo
  echo "适配说明: 见 ARTIFACT；上游门禁 run_tests.sh --no-lock 绿。"
} > "$PR_BODY"
PR_URL="$(gh pr create --repo "$UPSTREAM_REPO" --head "$BRANCH" \
  --title "factory: 反哺 etf-radar 工厂改进（${N_TOTAL} commits）" \
  --body-file "$PR_BODY")" || die "gh pr create 失败（分支已推送: ${PUSH_URL} ${BRANCH}）"
say "✓ 上游 PR: $PR_URL"

# --- 9. 账本回写（本仓 .factory/feedback-log.jsonl；提交但不推送） ---
PR_NUM="${PR_URL##*/}"
ARGS=(record "$PR_URL")
while IFS=$'\t' read -r sha subject; do ARGS+=("$sha:$subject"); done <<< "$PENDING"
python3 "$FACTORY/feedback.py" "${ARGS[@]}"
git -C "$REPO" add .factory/feedback-log.jsonl
git -C "$REPO" commit -q -m "chore(factory): 反哺账本 → ${UPSTREAM_REPO}#${PR_NUM}"
say "✓ 账本已提交（未推送，随下次人工推送）: .factory/feedback-log.jsonl"
say "完成: ${PR_URL}（人工 review & merge）"
