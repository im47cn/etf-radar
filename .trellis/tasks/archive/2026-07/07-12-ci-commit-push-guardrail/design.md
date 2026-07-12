# 技术设计 — data-commit 防hang护栏 composite action

## 方案总览

新建本地 composite action `.github/actions/commit-and-push/action.yml`，封装「幂等提交 +
防 hang 有界重试推送」。所有提交 `data/` 的 workflow 用一行 `uses:` 调用替换内联脚本。

选型理由（DRY > 局部 KISS）：当前 8 份几乎相同的 git 逻辑各自演化（有的有重试、有的没有、
有的有 timeout、有的没有），是典型重复代码病灶。集中到一个 action 后，护栏改一处生效全局。

## Action 契约

```yaml
# .github/actions/commit-and-push/action.yml
name: Commit and push data
description: 幂等提交指定路径到 main，防 hang 有界重试推送
inputs:
  paths:      { required: true,  description: "git add 的路径（空格分隔）" }
  message:    { required: true,  description: "commit 信息" }
  max-retry:  { required: false, default: "5" }
  user-name:  { required: false, default: "github-actions[bot]" }
  user-email: { required: false, default: "github-actions[bot]@users.noreply.github.com" }
outputs:
  changed:    { description: "true 表示产生了提交, false 表示无变更跳过" }
runs:
  using: composite
  steps:
    - shell: bash
      run: ...
```

## Action 内部逻辑（bash）

```bash
set -euo pipefail
export GIT_TERMINAL_PROMPT=0          # R2 防认证交互挂起
git config user.name  "${{ inputs.user-name }}"
git config user.email "${{ inputs.user-email }}"
git add ${{ inputs.paths }}
if git diff --staged --quiet; then
  echo "no changes, skip"; echo "changed=false" >> "$GITHUB_OUTPUT"; exit 0
fi
git commit -m "${{ inputs.message }}"
for i in $(seq 1 "${{ inputs.max-retry }}"); do
  git pull --rebase --autostash origin main \
    && git push \
    && { echo "changed=true" >> "$GITHUB_OUTPUT"; exit 0; }
  echo "push attempt $i failed, retry after backoff"
  git rebase --abort 2>/dev/null || true   # 冲突时清理，避免残留 rebase 态卡住下一轮
  sleep $((i * 5))
done
echo "::error::commit-and-push exhausted ${{ inputs.max-retry }} retries"; exit 1
```

要点：
- `--autostash`：容忍脏工作区（如 pull 前有未暂存变化），避免 rebase 因脏树卡住。
- 显式 `origin main`：避免依赖 tracking 配置。
- `git rebase --abort`：失败轮清理 rebase 半成品，否则下一轮 `pull --rebase` 会因「已在 rebase 中」报错空转。
- `GIT_TERMINAL_PROMPT=0` + job `timeout-minutes`：双保险，任何 git 子命令不再无限挂起。

## 各 workflow 改造映射

| workflow | 现状 | 改造 | changed 消费方 |
|---|---|---|---|
| cn-eod-archive | 裸 commit+rebase+push, step id=commit 有 `changed` 输出, 无 timeout | 换 action, 沿用 `id: commit` 取 `steps.commit.outputs.changed`; 加 timeout | Trigger deploy `if ... changed=='true'` |
| cn-refresh | 裸, 无 changed 输出, Trigger deploy 无条件 | 换 action; Trigger deploy 保持原语义(可选加 changed 判断, 不强制) | 无条件 deploy |
| us-refresh | 裸, 无 timeout | 换 action + timeout | 需核对 |
| holdings-refresh | 裸, 无 timeout | 换 action + timeout | 需核对 |
| stocks-spot-refresh | 裸, 无 timeout | 换 action + timeout | 需核对 |
| stocks-daily | 5 次 rebase 重试循环, data-bot, timeout:25 | 换 action(传 data-bot), 保留 timeout | 无(独立步骤) |
| stocks-history-backfill | reset-hard 覆盖取胜策略, timeout:120 | **不归并**, 仅原地加 `GIT_TERMINAL_PROMPT=0` | — |
| stock-industry-map | rebase 重试, data-bot, timeout:60 | 换 action(传 data-bot), 保留 timeout | 无 |

> 实施时逐个 `grep` 该 workflow 的 `steps.<id>.outputs` 与 `Trigger deploy` 的 `if`，
> 确保替换后 `changed` 语义与下游条件不回归（R3/AC）。

## 兼容性 / 风险

- **backfill 不归并（重要修正）**：实读发现 `stocks-history-backfill` 的提交逻辑不是 naive rebase，
  而是刻意的「我方整体重算获胜」策略——`git reset --hard origin/main` → 用重算结果覆盖 `data/stocks/` → commit → push（5 次重试）。
  这是为解决 backfill 整体重算与 daily 增量 append 的冲突而设计的（覆盖语义，非合并语义）。
  若归并进通用 `pull --rebase` action 会用合并/变基替换覆盖取胜 → 数据回归。
  **决策：backfill 保留原策略，仅原地补 `GIT_TERMINAL_PROMPT=0`**（它已有 `timeout-minutes:120` + 有界重试，hang 风险最低），不纳入 action 归并。
- **user 身份不统一**：高危 5 个用 `github-actions[bot]`，daily/industry-map 用 `data-bot`。
  action 增加可选输入 `user-name`/`user-email`（默认 `github-actions[bot]`），归并 daily/industry-map 时传 `data-bot` 保持不变。
- **concurrency 不变**：`data-refresh` 组三 workflow 仍串行排队，action 不触碰 concurrency。
- **timeout 取值**：裸提交类 job 主要耗时在数据抓取，提交本身秒级；job 级 timeout 取保守值
  （如 refresh 类 20min、archive 20min），既能兜底 hang 又不误杀正常抓取。实施时按各 job 现有耗时定。
- **回滚**：改动纯 YAML，`git revert` 单个 commit 即可整体回退；action 目录一并回退。

## 验证策略

1. `actionlint .github/workflows/*.yml`（若环境有；无则 `python -c "import yaml; yaml.safe_load(...)"` 逐文件解析）。
2. 选一个高危 workflow（如 `us-refresh` 或 `holdings-refresh`）`gh workflow run` 手动触发一次，
   确认提交成功、`changed` 输出正确、Trigger deploy 条件按预期。
3. 观察下一个交易日 cron 自然触发 `cn-eod-archive` 无 hang。
