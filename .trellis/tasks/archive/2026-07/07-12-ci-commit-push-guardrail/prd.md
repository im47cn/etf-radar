# data workflow 提交步骤防hang护栏

## 背景 / 问题

2026-07-11 `CN EOD Archive` run 在 `Commit archive` 步骤空转约 22 分钟后被取消：
数据已生成（前 6 步 success），但 `git commit → git pull --rebase → git push` 中的
`pull --rebase` 静默挂起（无 `GIT_TERMINAL_PROMPT=0`、无冲突策略、job 无 `timeout-minutes`），
直到被外部取消。同类 data-commit 逻辑在 8 个 workflow 里复制粘贴，既缺防 hang 护栏，又违背 DRY。

关联记忆：`ci-uvlock-drift-breaks-datacommit`（同为多 data workflow 竞争 main 写入导致 commit 步骤脆弱）。

## Goal

抽取统一的 composite action 承载「幂等提交 + 防 hang 重试推送」，让所有 data-commit workflow 复用，
根治重复逻辑并加固：任何 git 子命令不再能无限挂起，push 冲突可自动 rebase 重试并有界退出。

## 范围

覆盖全部提交 `data/` 到 `main` 的 workflow：
- 归并进 action（7 个）：
  - 裸提交无护栏（高危，重点）：`cn-refresh` `cn-eod-archive` `us-refresh` `holdings-refresh` `stocks-spot-refresh`
  - 已有 rebase 重试（DRY 归并，传 `data-bot`）：`stocks-daily` `stock-industry-map`
- **不归并，仅原地加护栏**：`stocks-history-backfill`——它是「reset-hard 覆盖取胜」策略（非 rebase），
  归并会造成数据回归；仅补 `GIT_TERMINAL_PROMPT=0`（已有 timeout+重试）。
- 排除：`membership-digest`（推送邮件，不提交 data）

## Requirements

- R1 新建 composite action（如 `.github/actions/commit-and-push/`），输入：`paths`(git add 路径) `message`(commit 信息)，输出：`changed`(true/false)。
- R2 action 内部：无变更时跳过并置 `changed=false`；有变更时 `commit`，再 `pull --rebase --autostash` + `push`，冲突/被拒时有界重试（≤5 次，退避 sleep），全程 `GIT_TERMINAL_PROMPT=0` 防认证挂起。
- R3 每个受影响 workflow 的提交步骤替换为调用该 action，保留原 `git add` 路径、commit 文案、`changed` 输出对下游 `Trigger deploy` 的 `if` 判断语义不变。
- R4 每个受影响 job 补 `timeout-minutes`（裸提交类此前完全没有），作为兜底上限。
- R5 不改动 workflow 的 trigger、concurrency 组、权限、trading-day 判断等既有行为。

## Acceptance Criteria

- [ ] 新 composite action 存在且被 7 个 workflow 引用；这些 workflow 的旧内联 git 逻辑删除。
- [ ] 5 个高危 workflow 的提交步骤不再含裸 `pull --rebase` + 无重试；均通过 action 走有界重试 + `GIT_TERMINAL_PROMPT=0`。
- [ ] `stocks-history-backfill` 保留 reset-hard 覆盖策略，仅新增 `GIT_TERMINAL_PROMPT=0`。
- [ ] 每个受影响 job 均有 `timeout-minutes`。
- [ ] `Trigger deploy` 等依赖 `changed`/`commit.outputs` 的下游步骤条件语义不回归。
- [ ] `actionlint`（若可用）/ YAML 解析通过；`workflow_dispatch` 手动触发一次高危 workflow 验证提交路径正常。

## Notes

- 无本地可跑的单测覆盖 CI YAML；验证靠 `actionlint` + 至少一次真实 `workflow_dispatch` 冒烟。
- `stocks-history-backfill` 实为 reset-hard 覆盖取胜策略，故排除归并（见 design 风险节）。
