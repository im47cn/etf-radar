# 执行计划 — data-commit 防hang护栏

## 顺序

### 阶段 A：建 action（基石）
1. 新建 `.github/actions/commit-and-push/action.yml`，按 design 的契约与 bash 逻辑实现。
   - 校验点：`inputs.paths/message/max-retry`、`outputs.changed`、`GIT_TERMINAL_PROMPT=0`、有界重试 + `rebase --abort` 清理。

### 阶段 B：改造高危 5 个（裸提交，重点）
逐个替换提交步骤为 `uses: ./.github/actions/commit-and-push`，保留原 `git add` 路径与 commit 文案，加 job `timeout-minutes`：
2. `cn-eod-archive.yml` — 保留 `id: commit`，下游 `Trigger deploy` 取 `steps.commit.outputs.changed`。
3. `cn-refresh.yml` — 核对 Trigger deploy 是否需 changed 条件（原为无条件，保持不回归）。
4. `us-refresh.yml`
5. `holdings-refresh.yml`
6. `stocks-spot-refresh.yml`

每改一个都先 `grep -nE "steps\.[a-z]+\.outputs|Trigger deploy|if:" <file>` 确认下游条件语义。

### 阶段 C：归并已有 rebase 重试的 2 个（传 data-bot）
7. `stocks-daily.yml` — 删 `for i in 1..5` 循环，换 action 并传 `user-name: data-bot`，保留 `timeout-minutes: 25`。
8. `stock-industry-map.yml` — 同上传 `data-bot`，保留 `timeout-minutes: 60`。

### 阶段 D：backfill 原地加护栏（不归并）
9. `stocks-history-backfill.yml` — 保留 reset-hard 覆盖取胜策略与 5 次重试，仅在脚本开头加
   `export GIT_TERMINAL_PROMPT=0`；不引 action，保留 `timeout-minutes: 120`。

## 验证命令（review gate）
- YAML 解析：`for f in .github/workflows/*.yml; do python3 -c "import yaml,sys; yaml.safe_load(open('$f')); print('ok $f')"; done`
- actionlint（若安装）：`actionlint .github/workflows/*.yml`
- 语义核对：`grep -rn "commit-and-push\|Trigger deploy\|timeout-minutes" .github/workflows/`
  确认 8 个 workflow 均 `uses` 新 action、均有 timeout、下游条件不变。

## 冒烟（可选，需用户授权触发真实 run）
- `gh workflow run holdings-refresh.yml --ref <branch>` 或 us-refresh，观察 Actions 日志：
  提交成功 / changed 输出 / 无 hang。

## 回滚点
- 每阶段一个逻辑单元；出问题 `git revert` 对应 commit。action 目录与 workflow 改动同批提交便于整体回退。

## 注意
- 全程不做 git commit/push（除非用户明确要求）；改动留在工作区待用户审阅。
- 不触碰 concurrency、trigger、permissions、trading-day 判断。
