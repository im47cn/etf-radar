#!/usr/bin/env bash
# feedback-upstream.sh — 反哺上游：本仓工厂改进 → 上游 PR（身份指针见 factory-local.json）。
#
# 定位：人工治理工具（dispatch/链永不调用；铁律 4 不受影响——本脚本不是
# dispatcher）。决策零 LLM：bash/git/gh 决定开不开 PR；omp 适配节点只产出
# 内容（clean cherry-pick 由脚本完成保持保真，AI 仅处理冲突与特化剥离），
# 与链同构：AI 产出、确定性门（上游测试门）做决策、人合并。
#
# 用法: feedback-upstream.sh [--dry-run]
#   --dry-run  只打印待反哺候选与上游漂移报告，零副作用
# env: UPSTREAM_PATH / UPSTREAM_REPO(默认取 factory-local.json，ADR-009 数据化)
#      NODE_TIMEOUT(适配节点预算，默认 30m)  GH_HOST(github 主机，默认 github.com)
#      PUSH_URL(显式推送目标，最高优先)  FREMOTE(显式基点 remote，镜像拓扑用)
set -euo pipefail

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "不在仓库内" >&2; exit 2; }
FACTORY="$REPO/.factory"
# ADR-009 引擎收口：omp_node 定义在 factory-lib.sh（本脚本只消费 omp_node；
# issue_* 出口函数不用——ISSUE 未定义无碍，函数体不在此触发）
source "${FACTORY}/factory-lib.sh"
# ADR-009 上游指针数据化：默认值自 factory-local.json（env 显式覆盖优先，
# 保留镜像拓扑逃生口）；fail-closed——配置缺失即终止。
UPSTREAM_PATH="${UPSTREAM_PATH:-$(python3 "$FACTORY/factory_lib.py" local-str upstream_path)}" \
  || { echo "factory-local.json upstream_path 不可用（fail-closed）" >&2; exit 2; }
UPSTREAM_PATH="${UPSTREAM_PATH/#\~/$HOME}"   # 配置 ~/ 形态的消费端展开（git -C 不做 tilde 展开，review R2-B2；原写法 \$HOME 是字面量非展开——git -C 收到 "$HOME/..." 原文即不可用）
UPSTREAM_REPO="${UPSTREAM_REPO:-$(python3 "$FACTORY/factory_lib.py" local-str upstream_repo)}" \
  || { echo "factory-local.json upstream_repo 不可用（fail-closed）" >&2; exit 2; }
FB_PREFIX="${FB_PREFIX:-$(python3 "$FACTORY/factory_lib.py" local-str feedback_branch_prefix)}" \
  || { echo "factory-local.json feedback_branch_prefix 不可用（fail-closed）" >&2; exit 2; }
SELF_ID="${SELF_ID:-$(python3 "$FACTORY/factory_lib.py" local-str repo_identity)}" \
  || { echo "factory-local.json repo_identity 不可用（fail-closed）" >&2; exit 2; }
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

say() { printf '%s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }

# --- 1. 待反哺候选（trailer ∨ bootstrap，− 账本；旧→新） ---
PENDING="$(python3 "$FACTORY/feedback.py" pending)" || die "候选收集失败"
# --- 1.5 疑似已随演化反哺（SHA 语义缺口）：内容经 cherry-pick+适配演化
#        反哺、SHA 未直樱桃的提交会永久 pending（源仓#66 实证，曾靠人工识别
#        孪生补录）。确定性文件集覆盖判定 → 跳过 + 亮清单，人工确认后
#        feedback.py record 补录清账（不自动入账：覆盖是强信号非等价证明）
SUPERSEDED="$(python3 "$FACTORY/feedback.py" superseded)" || die "superseded 收集失败"
if [ -n "$SUPERSEDED" ]; then
  say "疑似已随演化反哺 $(printf '%s\n' "$SUPERSEDED" | wc -l | tr -d ' ') 条（跳过；人工确认后 feedback.py record 补录）:"
  printf '%s\n' "$SUPERSEDED" | sed 's/^/  /'
  PENDING="$(printf '%s\n' "$PENDING" \
    | grep -vFf <(printf '%s\n' "$SUPERSEDED" | cut -f1) || true)"
fi
[ -z "$PENDING" ] && { say "无待反哺候选（账本已覆盖全部标记提交）"; exit 0; }
N_TOTAL="$(printf '%s\n' "$PENDING" | wc -l | tr -d ' ')"
say "待反哺候选: ${N_TOTAL} 个"

# --- 2. 上游可用性（2026-08-22 起上游为 bare 仓，无 .git 子目录与工作树） ---
git -C "$UPSTREAM_PATH" rev-parse --git-dir >/dev/null 2>&1 \
  || die "上游仓不可用: $UPSTREAM_PATH"


# --- 3. 上游准备：独立 worktree（不碰上游主工作区及其未提交改动，同链 D3 实践） ---
STAMP="$(date +%Y%m%d-%H%M%S)-$$"   # 秒级时戳同秒两跑必撞（源仓 PR#75 审查）：BRANCH/FB_DIR/WT 全撞；$$ 后缀跨触发隔离（macOS date 无 %N，PID 可移植）
FB_DIR="$FACTORY/artifacts/feedback-$STAMP"
mkdir -p "$FB_DIR/patches"
# 含时分秒（同 STAMP）：按日命名一天多跑必撞远端同名分支，push 被拒后
# 整链报废只能手工重放（2026-08-22 实证）；时戳分支随 PR 合并自动删除
BRANCH="${FB_PREFIX}-${STAMP}"
# 目录名与断言解耦：上游 repo_root 测试已改锚结构不变量（PR #22），
# checkout 目录名不再参与判定；保留 basename 仅为语义可读
WT="$FB_DIR/upstream-wt/upstream"
mkdir -p "$FB_DIR/upstream-wt"
GITUP=(git -C "$UPSTREAM_PATH")
# remote 拓扑随用户工作流变化（2026-08-22 实测：github remote 并入 origin 双推送，
# fetch=codeup 镜像 / push=codeup+github）。故不假设 remote 名：
# - 拉基点（FREMOTE）：①环境变量显式指定（镜像拓扑逃生口）；②fetch URL 确指
#   UPSTREAM_REPO 的 remote；③origin 兜底——其 fetch∨push URL 任一确指才可信
#   （双推镜像：fetch=codeup 无 slug、push=github 有），无关 origin 的 main 会
#   成为错误基点、PR 基于错误仓历史，故不可信即 fail（源仓#71 审查 1，fail-closed）
# - 推送显式解析 github push-URL 直推（主机经 GH_HOST 配置，GHE/别名可用），
#   避免多 pushurl 连带镜像
FREMOTE="${FREMOTE:-}"
if [ -z "$FREMOTE" ]; then
  FREMOTE="$("${GITUP[@]}" remote -v | awk -v repo="$UPSTREAM_REPO" \
    'index($0, repo) && $3 == "(fetch)" {print $1; exit}')"
fi
if [ -z "$FREMOTE" ]; then
  if "${GITUP[@]}" remote -v | awk -v repo="$UPSTREAM_REPO" \
      '$1 == "origin" && index($0, repo) {ok=1} END {exit !ok}'; then
    FREMOTE=origin
  else
    die "无可信基点 remote：无 fetch URL 指向 ${UPSTREAM_REPO}，origin 的 URL 亦不含（镜像拓扑可用 FREMOTE 显式指定）"
  fi
fi
"${GITUP[@]}" fetch "$FREMOTE" main --quiet
BASE="$("${GITUP[@]}" rev-parse --verify "$FREMOTE/main^{commit}")" \
  || die "无法解析 $FREMOTE/main"
# 主机不硬编码 github.com——GHE/SSH 别名经 GH_HOST 配置（与 gh CLI 同名同默认）；
# 显式 PUSH_URL 环境变量最高优先（源仓#71 审查 3）。index() 字面匹配免转义
if [ -z "${PUSH_URL:-}" ]; then
  PUSH_URL="$("${GITUP[@]}" remote -v | awk -v repo="$UPSTREAM_REPO" -v host="${GH_HOST:-github.com}" \
    'index($0, host) && index($0, repo) && $3 == "(push)" {print $2; exit}')"
fi
[ -n "$PUSH_URL" ] || die "上游 clone 无指向 github.com/${UPSTREAM_REPO} 的 push url（GH_HOST/PUSH_URL 可配置）"
# 跨仓对象：上游对象库没有本仓提交，cherry-pick 前临时挂源 remote 拉取
# （结束移除；拉入对象随后不可达，交由上游 gc，无残留引用）。
REMOTE_ADDED=0   # cleanup 在 set -u 下读它；remote add 前任何 die（dry-run/worktree/fetch 失败）都会先进 EXIT trap（源仓 PR#75 审查）
# push 失败保留现场标志（cleanup 检查）：适配成果只存在于本地 worktree，
# 失败即删 = 全丢。账本未记（PR 未开），重跑会重复反哺——保留供手工
# push/开 PR 或排查，恢复指引随 die 输出
KEEP_WT=0
cleanup() {
  if [ "${KEEP_WT}" = 1 ]; then
    say "现场已保留: worktree ${WT} 分支 ${BRANCH}（产物: ${FB_DIR}）"
    return
  fi
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

# 跨仓对象：上游对象库没有本仓提交，cherry-pick 前临时挂源 remote 拉取
# （结束移除；拉入对象随后不可达，交由上游 gc，无残留引用）。
# dry-run 出口之后才做：remote add 属上游配置变更，只读模式不碰
if "${GITUP[@]}" remote add feedback-src "$REPO" >/dev/null 2>&1; then
  REMOTE_ADDED=1
else
  # 已存在则校验 URL 确指本仓后复用——存在≠正确，指向他仓会让 fetch/cherry-pick
  # 读到错误对象源（源仓#71 审查 2）；仅本次添加的才 cleanup 移除（防误删用户配置）
  EXISTING_SRC="$("${GITUP[@]}" remote get-url feedback-src 2>/dev/null || true)"
  [ -n "$EXISTING_SRC" ] && [ "$EXISTING_SRC" = "$REPO" ] \
    || die "既有 feedback-src 指向「${EXISTING_SRC:-空}」≠ 本仓 ${REPO}，拒绝复用（请手工处理）"
fi
"${GITUP[@]}" fetch -q feedback-src main

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

# patches/<sha9>.patch + manifest.json 生成在 feedback.py adapt-prep
# （2026-08-28 自此处 heredoc 下沉：git 子进程编排归 Python，铁律 4；
# 亦是 killpg 门[只扫 *.py]与 pipe 门[只扫 *.sh]双盲缝隙的收口）
python3 "$FACTORY/feedback.py" adapt-prep "$FB_DIR" "$PENDING" \
  ${CONFLICTED[@]+"${CONFLICTED[@]}"}
PROMPT="$(cat "$FACTORY/prompts/feedback-adapt.md")


——任务参数:
- FEEDBACK_DIR: $FB_DIR
- 上游 worktree: ${WT}（你在此工作树上操作；基点含上游最新 main）
- 候选数: ${N_TOTAL}（manifest.json 为准）
- 下游仓（本仓）身份: ${SELF_ID}；上游仓: ${UPSTREAM_REPO}"
say "==> 适配节点（fresh context 进程，预算 ${NODE_TIMEOUT:-30m}）"
# 越界检测基线（源仓）：适配节点曾在源仓自行开分支/提交/开 PR（源仓#71
# 事故——prompt 当时只约束上游 git）。节点自身的 push/PR 无法本地拦截
# （凭据是环境态），此指纹保证脚本自身的推送/入账前发现越界并终止。
# 分支表 = 硬判据（dispatcher 归位只 checkout 不建分支，零误报源）；
# HEAD 漂移 = 仅告警（dispatcher factory/base 归位是已知良性源，不可区分）
SRC_HEADS_BEFORE="$(git -C "$REPO" for-each-ref --format='%(refname)' refs/heads/ | sort)"
SRC_HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD)"
NODE_RC=0
omp_node "$WT" "$FB_DIR/adapt.log" "${NODE_TIMEOUT:-30m}" -- "$PROMPT" || NODE_RC=$?
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
# 越界检测（源仓，源仓#71 事故收口）：分支表变动 = die（推送/入账前拦截）；
# HEAD/分支漂移 = 告警（dispatcher 归位不可区分，人工甄别）；findings.md
# = 节点按 prompt 契约上报的源仓/工具链缺陷，人工处置
SRC_HEADS_AFTER="$(git -C "$REPO" for-each-ref --format='%(refname)' refs/heads/ | sort)"
[ "$SRC_HEADS_BEFORE" = "$SRC_HEADS_AFTER" ] \
  || die "适配节点越界：源仓分支表变动（git for-each-ref 甄别；产物 ${FB_DIR}）"
if [ "$(git -C "$REPO" rev-parse HEAD)" != "$SRC_HEAD_BEFORE" ]; then
  say "⚠ 源仓 HEAD 在节点运行期间漂移（或为 dispatcher 归位；请人工确认）"
fi
[ -f "$FB_DIR/findings.md" ] && {
  say "⚑ 节点上报源仓/工具链缺陷（人工处置，findings.md）:"
  sed 's/^/  /' "$FB_DIR/findings.md"
}

# --- 7. 上游门禁：红 → 不开 PR，只收报告 ---
# gauntlet（不是纯 pytest 门）: 2026-08-22 事故——适配节点产出 BRANCH 未定义
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
"${GITW[@]}" push -q --no-verify "$PUSH_URL" "$BRANCH" || {
  KEEP_WT=1
  die "push 失败——现场已保留（worktree ${WT}，分支 ${BRANCH}）。恢复: cd ${WT} && git push --no-verify ${PUSH_URL} ${BRANCH}，或排查后手工清理: git -C ${UPSTREAM_PATH} worktree remove --force ${WT}"
}
PR_BODY="$FB_DIR/pr-body.md"
{ echo "自 ${SELF_ID} 反哺工厂改进（一候选一提交，clean pick 保真 / conflicted 适配）。"
  echo
  printf '%s\n' "$PENDING" | while IFS=$'\t' read -r sha subject; do
    echo "${sha:0:9}  $subject"
  done
  echo '```'
  echo
  echo "适配说明: 见 ARTIFACT；上游门禁 gauntlet 全层绿。"
} > "$PR_BODY"
# base 显式（PR #116）：上游 fetch/补基硬编码 main，不猜 gh 默认分支
PR_URL="$(FACTORY_HOSTING=github python3 "${REPO}/.factory/hosting.py" pr create \
  --repo "$UPSTREAM_REPO" --head "$BRANCH" \
  --base main \
  --title "factory: 反哺 ${SELF_ID} 工厂改进（${N_TOTAL} commits）" \
  --body-file "$PR_BODY" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("url") or "")')" \
  || die "hosting pr create 失败（分支已推送: ${PUSH_URL} ${BRANCH}）"
say "✓ 上游 PR: $PR_URL"
# PR 落定后立即删本地裸分支（远端 PR 分支不受影响）：上游 bare 仓本地分支
# 不随 PR 合并自动消失，feedback-upstream 又只 push 不清理——攒下的死引用
# 会污染 for-each-ref / 补基判断，还可能与下次同名分支撞车（2026-08-24
# 清理时发现 20260822 两支残留实证）。失败仅告警：远端分支与 PR 已成立，
# 本地引用只是缓存，残留可人工删。
"${GITUP[@]}" branch -qD "$BRANCH" >/dev/null 2>&1 \
  || say "⚠ 本地分支 $BRANCH 删除失败（远端 PR 不受影响，可人工清理）"

# --- 9. 账本回写（本仓 .factory/feedback-log.jsonl；提交但不推送） ---
PR_NUM="${PR_URL##*/}"
ARGS=(record "$PR_URL")
while IFS=$'\t' read -r sha subject; do ARGS+=("$sha:$subject"); done <<< "$PENDING"
python3 "$FACTORY/feedback.py" "${ARGS[@]}"
git -C "$REPO" add .factory/feedback-log.jsonl
git -C "$REPO" commit -q -m "chore(factory): 反哺账本 → ${UPSTREAM_REPO}#${PR_NUM}"
say "✓ 账本已提交（未推送，随下次人工推送）: .factory/feedback-log.jsonl"
say "完成: ${PR_URL}（人工 review & merge）"
