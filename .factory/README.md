# .factory — 维护工厂（S2 派发形态：dispatch.sh + 状态同步器）

> 状态：S1。人类只做两件事：**写 issue、合并 PR**。
> 治理依据：[MISSION.md](../MISSION.md)（宪法，工厂永不可改）。
> 设计文档：[docs/design/factory-harness-design.md](../docs/design/factory-harness-design.md)。

## 组件

| 路径 | 角色 |
|---|---|
| `fix-issue.sh` | 全链入口：一个 issue 进，一个待人工合并的 PR 出 |
| `guard.py` | 周界锁（前缀匹配，fail-closed，铁律 3） |
| `mutations/run.py` | 门灵敏度冒烟（注入缺陷→断言拦截→字节还原，铁律 5） |
| `prompts/*.md` | 六个 AI 节点提示词（版本化、引擎无关，禁内联） |
| `feedback-upstream.sh` | 反哺上游：可泛化改进 → awesome-rules PR（人工工具，链不调用） |
| `feedback.py` + `feedback-log.jsonl` | 反哺决策层（候选收集/漂移分类）与已反哺账本 |
| `artifacts/issue-N/` | 链产物（运行时输出，勿提交 git） |

## 前置条件

- `omp` CLI（AI 节点引擎；每节点独立进程 = 物理级 fresh context）
- `gh` 已认证（取 issue、建 PR）
- `python3`（guard / mutations / JSON 解析）

## 快速开始

```bash
# 0. 干跑：只打印链步骤，不执行、不取 issue
.factory/fix-issue.sh 42 --dry-run

# 1. 在 GitHub 上写好 issue（这是人类输入点）

# 2. 真跑（triage 拒绝则链自然终止，exit 0）
NODE_TIMEOUT=30m .factory/fix-issue.sh 42
```

## 链结构

```
  → triage（裁决 accept|reject；落标 factory:accepted|rejected，
           reject 附判据明细回执评论到 issue 后终止）
  → git checkout -b factory/issue-N
  → prime（研究笔记，不做设计）
  → plan（任务级计划 plan.json，含每任务 verify 命令）
  → implement（逐任务执行，周界任务跳过标 blocked，
               末尾跑 final_gate 存 tests-output.txt，提交不推送）
  → review（链内自审，修小问题；独立判断不在此）
  → 确定性门：guard.py --files <main...分支改动> 
  → holdout（独立验证器：omp --no-tools，输入白名单
             issue 标题 + tests-output.txt，全部内联）
  → PASS → gh pr create --label factory:needs-review（人类合并）
  → FAIL → 不建 PR，链终止
```

节点失败（非零退出或产物缺 `ARTIFACT:` 行）= 整链终止，
日志见 `artifacts/issue-N/<节点名>.log`。

## 产物清单（artifacts/issue-N/）

| 文件 | 产生者 | 说明 |
|---|---|---|
| `issue.json` | 链脚本 | `gh issue view --json` 原始数据 |
| `triage.json` | triage | verdict / priority / reasons |
| `tests-output.txt` | implement（review 修复后刷新） | final_gate 完整输出 + 触及套件 `-v` 测试名证据（holdout 唯一证据源；静默点号输出 = 证据饥饿，holdout 将合法 FAIL） |
| `plan.json` | plan | tasks[] 每项含 verify 命令；forbidden 周界清单 |
| `implement.md` | implement | 执行日志（每任务改动与 verify 结果） |
| `review.md` | review | 自审报告（已修复 / 待人类） |
| `reject-receipt.md` | 链脚本 | 拒绝回执正文（已评论到 issue；评论失败时手动补发源） |

## S2 派发器与标签同步器

```bash
bash .factory/dispatch.sh --dry-run        # 单轮演练（DRY=1 环境变量等价）
bash .factory/dispatch.sh                  # 单轮：sync → PR结果 → 重派 → 队列
bash .factory/dispatch.sh --watch          # 常驻，默认 1800s（或 cron */30 单轮）
bash .factory/factory-state.sh sync --all  # 标签收敛（幂等，可随时/cron 跑）
bash .factory/factory-state.sh sync 2 --plan   # 单 issue 计划模式（只打印）
python3 -m pytest .factory/test_state.py -o addopts= -q   # 状态机测试
```

架构（防"转移实现一半"）：

- **标签 = 事实的纯函数**（`state.py plan_phase`）。PR 存在性、
  reviewDecision、needs-fix 的 label-add 事件计数、`[factory:rejected]`
  标记评论——从这些仓库可见事实整体推导目标态，`factory-state.sh`
  幂等收敛。没有散落的转移代码，漏写转移这类缺陷在结构上不存在。
- **锁例外**：`triaging`（链写）/`in-progress`（dispatch 写）是运行中
  声明，sync 永不触碰；终态（rejected/closed）清理除外（漂移自愈）。
- **转移表即 spec**：`state.py TRANSITIONS` 是唯一权威；
  `test_table_full_coverage` 强制每条边有场景 fixture，表与代码漂移即红。
- **计数契约**：needs-fix 轮次 = PR 上该标签 add 事件数。dispatch 重派时
  必须移除 needs-fix（标签滞留则事件不再触发、计数冻结）；
  ≤2 轮后第 3 次打回自动转 needs-human。
- **auto-merge 受 A5 门控**：`FACTORY_AUTO_MERGE=1` 且
  `.factory/metrics/auto-merge-unlocked` 存在才 merge；否则 approved
  只打标签，人类合并。mutations kill-rate ≥80% 前不得开启。
- **单实例假设**：GitHub 无原子换标签，claim（accepted→in-progress）
  的互斥由单 dispatcher 部署保证，sync 收敛并发漂移。
- **链失败**：fix-issue.sh 非零退出 → trap 清 triaging/accepted/
  in-progress → issue 回零标签态，人工重投。

派发器环境变量：`MAX_PARALLEL=4`、`FACTORY_MERGE_METHOD=merge`、
`INTERVAL=1800`、`GH_REPO=<owner/repo>`（无 github remote 时显式指定）。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `NODE_TIMEOUT` | `30m` | 单 AI 节点 `omp --max-time` 预算 |

## 门单独使用

```bash
# 周界锁（退出码 0=干净 1=触碰周界 2=门自身错误 fail-closed）
python3 .factory/guard.py --base origin/main [--head HEAD]   # PR 模式
python3 .factory/guard.py --files <path> [<path> ...]        # 列表模式
git diff --name-only base...head | python3 .factory/guard.py # stdin 模式

# 门灵敏度冒烟（退出码 0=全拦截 1=有 FAIL 2=配置错 3=还原失败 4=有 SKIP）
python3 .factory/mutations/run.py [--only G-01,G-03]
```

## 反哺上游（awesome-rules）

本工厂移植自 awesome-rules，两侧各自演化。反哺 = 把本仓对工厂的**可泛化**
改进以 PR 形式推回上游，人工合并；上游漂移只报告不自动吸收。

```bash
bash .factory/feedback-upstream.sh --dry-run   # 只看候选 + 漂移报告，零副作用
bash .factory/feedback-upstream.sh             # 完整管线：pick→AI适配→上游门禁→PR
```

- **候选标记**：可泛化的工厂提交在 commit message 尾部加
  `Upstream-Feedback: yes` trailer（判断在提交时做出）；历史提交经
  `feedback.py BOOTSTRAP_CANDIDATES` 一次性补录。
- **管线**：clean cherry-pick 由脚本完成（保真）；conflicted 与特化剥离交
  omp 适配节点（`prompts/feedback-adapt.md`）；上游 `scripts/run_tests.sh
  --no-lock` 绿才开 PR，红只收报告。一候选一提交，只允许动 `.factory/`。
- **账本**：`.factory/feedback-log.jsonl`（append-only）记录已反哺 SHA 与
  上游 PR 号，防重复反哺；`factory-state.sh --all` 末尾输出待反哺计数。
- env：`UPSTREAM_PATH`（默认 `~/sources/awesome-rules`）、
  `UPSTREAM_REPO`、`NODE_TIMEOUT`。

## 移植记录（awesome-rules → etf-radar，2026-08-21）

本工厂已按上游移植清单完成适配，四处变更如下：

1. **MISSION.md**：重写为 etf-radar 使命（数据流水线/前端/测试/文档维护），
   周界覆盖治理面（CLAUDE.md/CONVENTIONS）、质检线（.factory/scripts/.github）、
   数据面（data/config/supabase，机器写入面与人类参数）、依赖与发布面
   （pyproject/uv.lock/package*.json/.gitignore/.mcp.json/.claude/）。
2. **guard.py PERIMETER**：与 MISSION 周界同步重写，self_check 双向核对。
3. **测试门**：新建 `scripts/run_tests.sh`（mypy strict + ruff + pytest --cov +
   diff-cover / tsc -b + eslint + vitest --coverage，与 pre-push、CI 同口径），
   另提供 `--evidence backend|frontend` verbose 证据段模式（holdout 证据源）。
   mutations kill rate 已在本仓库重证：6/6 拦截 + 1/1 负例放行。
4. **提示词与脚本**：triage/prime/review/pr-review 仓库身份与依据改为
   etf-radar（docs/CONVENTIONS.md）；链脚本 remote 取 origin；
   factory_lib.evidence_suites 映射改为 backend/frontend 两套件。

## S1/S2 已知边界

- S1 手动跑 `fix-issue.sh`；S2 用 `dispatch.sh`（本仓库现已内置）。
  auto-merge 仍默认关闭（A5：mutations kill-rate 未证 ≥80%）。
  标签状态机唯一权威在 `state.py TRANSITIONS`（12 条边全覆盖有测试）。
- holdout 输入白名单是提示词纪律级约束，S2+ 换 SDK
  `restrictToolNames` 物理化（设计文档 §7）。
- `--fill` 生成的 PR 标题质量依赖 implement 的 commit 信息。
- needs-fix 重派复用 `fix-issue.sh`（`checkout -b || true` 落在既有分支），
  全节点重跑；链内断点续跑（resume）未实现。
