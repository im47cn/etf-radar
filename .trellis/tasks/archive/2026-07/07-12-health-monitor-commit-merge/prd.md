# health-monitor 提交步骤归并 commit-and-push

## 背景

上一任务 `07-12-ci-commit-push-guardrail` 抽出 `.github/actions/commit-and-push`，7 个 data workflow 已归并。
遗留 `health-monitor.yml` 的 `Commit heal_state` 步骤仍内联手写 `git pull --rebase origin main` 5 次重试循环，
未复用 action，缺 `GIT_TERMINAL_PROMPT=0` 护栏。本任务收口最后一个。

## Goal

`health-monitor.yml` 的提交步骤复用 `commit-and-push` action，行为语义不回归。

## 关键约束（易错点）

- **保留 token 注入**：health-monitor 的 checkout 关闭了凭据持久化，靠 `git remote set-url origin
  https://x-access-token:${DATA_BOT_PAT}@...` 注入 token 供 push（现第 70 行）。此步**必须保留**——
  作为调用 action 前的前置 `run` step（git remote 配置写盘、同 job 跨 step 持久，action 的 push 会用它）。
- **保留 dry-run 门控**：`if: env.HEALTH_DRY_RUN != '1' && != 'true'` 语义不变。
- **user 传 `data-bot`**（原用 data-bot，不能变默认 github-actions[bot]）。
- **date 陷阱**：原 message `chore: health heal_state $(date -u +%FT%TZ)`——`$(date)` 在 `with:` 里是死字符串，
  须前置 meta step 写 `$GITHUB_OUTPUT` 再 `${{ steps.*.outputs.* }}` 引用（格式 `%FT%TZ`）。
- 保留 `timeout-minutes: 15`、`concurrency: health-monitor`、`data/health/` 路径不变。

## Acceptance Criteria

- [ ] `Commit heal_state` 的内联 5 次重试循环删除，改 `uses: ./.github/actions/commit-and-push`。
- [ ] `git remote set-url`（token 注入）保留为前置 step；dry-run 门控 `if` 保留。
- [ ] 传 `user-name: data-bot` / `user-email: data-bot@...`、`paths: data/health/`、message 经 meta step 生成（`%FT%TZ`）。
- [ ] `timeout-minutes: 15` 保留。
- [ ] YAML 解析 + actionlint 通过；工作树无裸 `pull --rebase`（除 backfill 的 reset-hard 例外）。

## Notes

- 单文件轻量改动，沿用上一任务已验证的 action 契约，不新增 action 变更。
