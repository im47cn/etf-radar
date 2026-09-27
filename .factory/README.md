# .factory — 维护工厂（S2 派发形态：dispatch.sh + 状态同步器）

> 本 README 自上游 awesome-rules 重移植（2026-09-27，锚点 3f2a89db），机制
> 描述与上游同源；本仓定制见下节。

## 本仓定制（相对上游）

- **派发**：中央 hub（`~/.config/factory/dispatch-all.sh` + `repos.conf`，
  LaunchAgent `com.im47cn.factory.hub` 每 600s）kick 本仓
  `cron-dispatch.sh`，多仓共用一个调度器；单仓直跑 dispatch.sh 亦可。
- **租约**：单写者模式（`SUPABASE_DB` 未设 → 本地锁降级，每轮 stderr
  告警 single-writer mode）——本仓只在一台机器跑工厂，无需仲裁层。
- **Sourcery**：`tools/git/lefthook/sourcery-gate.sh` + `.sourcery.yaml`
  已移植（opt-in 闸；规则豁免清单本地化，去上游 `_vendored` 项）。
- **并行门**：`parallel_gate` 两段（backend/frontend），段体收敛在
  `scripts/run_tests.sh --segment`（单一真相源，JSON 只登记编排）。
- **日回归**：未启用（见 S2 节注记）；数据面新鲜度由仓库自有
  GitHub Actions health_monitor 生态负责。
- **上游同步**：full 面经 `sync-from-upstream.sh --apply` 追平，锚点
  `upstream-lock.json`；漂移检查 `upstream-sync-check.sh <upstream>`。

> 状态：S2（人工路径收口中；设计文档 §8 判据为准）。人类只做两件事：**写 issue、合并 PR**。
> 治理依据：[MISSION.md](../MISSION.md)（宪法，工厂永不可改）。
> 设计文档：[docs/design/factory-harness-design.md](../docs/design/factory-harness-design.md)。

## 组件

| 路径 | 角色 |
|---|---|
| `fix-issue.sh` | 全链入口：一个 issue 进，一个待人工合并的 PR 出 |
| `guard.py` | 周界锁（前缀匹配，fail-closed，铁律 3） |
| `mutations/run.py` | 门灵敏度冒烟（注入缺陷→断言拦截→字节还原，铁律 5） |
| `prompts/*.md` | 八个 AI 节点提示词（triage/prime/plan/implement/review/holdout/pr-review/feedback-adapt；版本化、引擎无关，禁内联） |
| `artifacts/issue-N/` | 链产物（运行时输出，勿提交 git） |
| `factory-lease.sh` | 租约仲裁客户端（claim/心跳/出口围栏；fail-closed，source 引入） |
| `db/schema.sql` | 仲裁层 schema（Supabase/任何 Postgres，服务端原子，幂等迁移） |
| `dispatch.sh` | S2 派发器入口 shim（编排下沉 `factory_lib.py dispatch` 子命令，ADR-005；CLI/env 契约不变，零 LLM） |
| `cron-dispatch.sh` | hub kick 入口（LaunchAgent 600s → 锁 + dispatch 单轮） |
| `factory-state.sh` | 标签同步器（托管平台事实 → state.py 推导 → 幂等收敛） |
| `hosting.py` + `tests/test_hosting.py` | 托管平台抽象层（ADR-008）：中立 schema（issue/pr/label history）+ GitHub（gh）/Codeup（云效 oapi）双适配器；核心脚本零 gh 直调。Codeup 评论标记模型（#66）：add 标记评论/置 resolved/changes-requested 手势承载类标与轮次语义，全链状态机可跑 |
| `validate-pr.sh` | S3 PR 门禁链（guard → tests → docstring(可选) → AI 评审 → holdout，人类合并前独立验证） |
| `state.py` + `tests/`（含 test_state.py） | 状态机权威（TRANSITIONS 唯一 spec）与全套测试 |
| `feedback.py` + `feedback-upstream.sh` | 本仓工厂改进反哺上游（决策零 LLM，AI 仅适配内容；上游指针 = factory-local.json，ADR-009） |
| `breaker.sh` | R4 成本熔断门（fix-issue/dispatch/cron-dispatch/triage-batch 四入口共用接线点，透传 factory_lib breaker 码） |
| `factory-lib.sh` + `factory_lib.py` | 链副作用共享库（issue 评论唯一出口/拒绝单一动作/租约围栏钩位）+ python 工具箱（timeout 分级预算/breaker/回执解析 + dispatch 进程编排：并发槽/收割/硬锁，ADR-005 + parallel-gate 并行测试门编排：段 fan-out/保守档段内并行/失败日志保留，ADR-016）。`omp_node()` 是 omp CLI 唯一执行点（ADR-009 引擎收口）——换引擎只改此函数 |
| `factory-local.json` | 工厂本地化配置（M4 + ADR-009）：perimeter/reject_guidance（guard 判据）+ repo_identity/reading_scopes/review_basis/final_gate_cmd/docstring_gate_cmd（可选门，缺省不启用）/parallel_gate（并行测试门段清单，ADR-016）/pr_review_skills（prompt 仓库参数与门命令）+ upstream_repo/upstream_path/feedback_branch_prefix（反哺上游指针）——链脚本与 prompts 零本地化的全部数据载体；改后须重跑 mutations 重证 |
| `upstream-sync-check.sh` | M2 上游同步检查（dispatch 轮末）：full 漂移→确定性 PR 流；local 漂移→needs-human issue；无凭据降级仅报告 |
| `sync-from-upstream.sh` + `DISTRIBUTION.json` | M1 上游同步：三态分发清单（full/local/skip）+ 下游拉取（--check 门禁/--apply 追平+锚点）；B1（ADR-011）`--repo` 中心驱动 + `--commit` 单提交落库 + blame-ignore 滞后一条 |
| `downstream-check.sh` + `downstream.local.json` | B2 中心集中巡检（ADR-011）：10 仓清单（gitignored 本地数据，ADR-012——tracked `downstream.json` 仅空模板）；`--check` 逐仓漂移检查 + `--apply-commit` 漂移仓单提交追平；一律 `--anchor main` 跑中心版脚本；漂移 osascript 通知（`FACTORY_NO_NOTIFY=1` 关断） |


## 前置条件
- `omp` CLI（AI 节点引擎；每节点独立进程 = 物理级 fresh context）
- `python3`（guard / mutations / hosting / JSON 解析）
- 托管平台凭据（ADR-008，二选一）：GitHub = `gh` 已认证（默认）；
  Codeup = `YUNXIAO_ACCESS_TOKEN` + `CODEUP_ORG_ID` + `CODEUP_REPO_ID|PATH`
  （注意：Codeup 工作项读写面已实装（#67）；MR 面缺口 (b)(c)（类标无
  Unlink、无标签事件史）已由评论标记模型承载（#66，ADR-008 附记），
  全链状态机可跑；可用面 = MR 读写/评论/合并/类标 Link + 标记评论 +
  issue 全套（需 `CODEUP_SPACE_ID`/`WORKITEM_TYPE_ID`/`ASSIGN_USER_ID`））
- `SUPABASE_DB` 仲裁层 PG 连接串（Supabase pooler 或自建 Postgres；未设 = 单写者模式本地锁降级，见「租约仲裁」）

## 快速开始

```bash
# 0. 干跑：只打印链步骤，不执行、不取 issue
.factory/fix-issue.sh 42 --dry-run

# 1. 在 GitHub 上写好 issue（这是人类输入点）

# 2. 真跑（triage 拒绝则链自然终止，exit 0）
NODE_TIMEOUT=30m .factory/fix-issue.sh 42
```

### 重投（对 rejected 不服）

评论补充上下文**不触发**任何自动化——triage 节点已内联 issue 评论，
评论只是下一轮裁决的输入。重投是明确手势：

```bash
gh issue edit 42 --remove-label factory:rejected   # 维护者表达"重审"意图
NODE_TIMEOUT=30m .factory/fix-issue.sh 42           # 重跑链，triage 全新评估
```

链 accept 时自动清掉上轮 rejected 残留（fix-issue.sh 标签转移），
不会三标签并存。

## 链结构

```
  → triage（裁决 accept|reject；落标 factory:accepted|rejected，
           reject 附判据明细回执评论到 issue 后终止）
  → git worktree add -B factory/issue-N .factory/worktrees/issue-N（基 main）
  → prime（研究笔记，不做设计）
  → plan（任务级计划 plan.json，含每任务 verify 命令）
  → implement ↔ review ralph 修复轮（implement 逐任务执行，周界任务
               跳过标 blocked，末尾跑 final_gate 存 tests-output.txt 与
               docstring 门（docstring_gate_cmd 配置时）存 docstring-output.txt，
               提交不推送；review 链内自审修小问题，可行动发现落
               ralph-todo.md——非空即回流 implement 再修再审，
               ≤FACTORY_RALPH_MAX 轮（默认 2），耗尽的残留随 review.md
               进 PR；独立判断不在此，在 holdout）
  → 确定性门：guard.py --files <main...分支改动> 
  → holdout（独立验证器：omp --no-tools + --config omp-isolated.yml
             issue 标题 + tests-output.txt，全部内联）
  → PASS → gh pr create --label factory:needs-review（人类合并）
  → FAIL → 不建 PR，链终止

重投：人类移除 rejected 标签后重跑链（评论本身不触发——它是下一轮
triage 的输入，不是决策手势；标签才是）。
```

节点失败（非零退出，或声明的产物文件缺失/未更新）= 整链终止，
日志见 `artifacts/issue-N/<节点名>.log`。产物存活判定（B1，
2026-09-05）：prompts 声明的固定产物文件存在且 mtime ≥ 节点起点标记
——容忍 stdout 末行格式漂移（#131 实测：计划完整产出但末行写
"产物：…"、无 `ARTIFACT:` 前缀，被旧 grep 误杀）；stdout 末行
`ARTIFACT: $ISSUE_DIR/<file>` 仍是节点协议要求与诊断依据，不再是
存活判定的唯一信号。

## 产物清单（artifacts/issue-N/）

| 文件 | 产生者 | 说明 |
|---|---|---|
| `issue.json` | 链脚本 | `gh issue view --json` 原始数据 |
| `triage.json` | triage | verdict / priority / reasons |
| `tests-output.txt` | implement（review 修复后刷新） | final_gate 完整输出 + 触及套件 `-v` 测试名证据（holdout 唯一证据源；静默点号输出 = 证据饥饿，holdout 将合法 FAIL） |
| `docstring-output.txt` | implement（review 修复后刷新） | docstring 门输出（配置 docstring_gate_cmd 时由其命令生成；阈值/格式由各仓检查器自定；门失败 = 链终止） |
| `plan.json` | plan | tasks[] 每项含 verify 命令；forbidden 周界清单 |
| `implement.md` | implement | 执行日志（每任务改动与 verify 结果） |
| `review.md` | review | 自审报告（已修复 / 待人类） |
| `ralph-todo.md` | review | 可行动发现回流清单（非空触发修复轮；审查通过即删除；轮次耗尽的残留见 review.md） |
| `reject-receipt.md` | 链脚本 | 拒绝回执正文（已评论到 issue；评论失败时手动补发源） |

## S2 派发器与标签同步器

```bash
bash .factory/dispatch.sh --dry-run        # 单轮演练（DRY=1 环境变量等价）
bash .factory/dispatch.sh                  # 单轮：sync → PR结果 → 重派 → 队列
bash .factory/dispatch.sh --watch          # 常驻，默认 300s（或 cron 单轮；断档教训见文末）
sh .factory/cron-dispatch.sh               # hub(LaunchAgent 600s) 的 kick 入口：锁 + triage + dispatch 单轮
bash .factory/factory-state.sh sync --all  # 标签收敛（幂等，可随时/cron 跑）
bash .factory/factory-state.sh sync 2 --plan   # 单 issue 计划模式（只打印）
python3 -m pytest .factory/tests/test_state.py -o addopts= -q   # 状态机测试
# 本仓日回归未启用：daily-regression.sh 层命令（badcase/gauntlet/doc-freshness）
# 为上游仓特定；文件已随 skip 分发同步但 inert，启用需先本地化层清单
```

架构（防"转移实现一半"）：

- **标签 = 事实的纯函数**（`state.py plan_phase`）。PR 存在性、
  reviewDecision、needs-fix 的 label-add 事件计数、`[factory:rejected]`
  标记评论——从这些仓库可见事实整体推导目标态，`factory-state.sh`
  幂等收敛。没有散落的转移代码，漏写转移这类缺陷在结构上不存在。
- **链写 issue 评论唯一出口 = `issue_comment()`**（factory-lib.sh，
  fix-issue.sh / triage-batch.sh 共享 source）：发送前 `factory_lib sanitize`
  原地中和正文中的 `[factory:rejected]` 子串——链产正文（LLM reasons 等）
  可能回显用户评论里的标记，携带即被 state.py 标记评论通道识别为人工
  覆盖、永久钉死 rejected。中和在出口统一执行，渲染器不各自记得；
  中和失败 fail-closed 不发送。新增链评论点必须走它。
- **拒绝 = 单一动作 `issue_reject()`**（factory-lib.sh）：落标
  （→ factory:rejected）与判据回执评论一次收口，链/批次两入口共用。
  落标失败先复核远端标签态（#207 事故：gh 假阴性——变更已落而客户端
  报非零）：factory:rejected 在列即按已落定继续回执，确证缺失才中止
  ——两半动作不因传输层假阴性脱节（ADR-015）。
  历史教训：两入口曾各自只做一半——链路发回执不落标、批次落标不发回执
  （#59 二次拒绝静默），动作散落必然被漏做一半。
- **hosting 仅传输层**（ADR-008）：`hosting.py` 是 issue 评论/标签副作用
  出口（`issue_comment()`/`issue_label_swap()`）的下层传输，链/批次/回归
  脚本不得绕过 factory-lib 直调 hosting 写 issue 副作用——`gauntlet`
  `lint-factory-hosting-exit` 门机械化盯防（负控制 NC12）。issue/pr 创建
  与 PR 侧写不在收口范围（S3/M2 无 issue 租约上下文，PR 标签漂移由
  sync 兜底收敛）。
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
- **单实例假设 → 租约仲裁**：GitHub 无原子换标签，claim（accepted→
  in-progress）的单机互斥仍由 dispatcher 锁保证；跨机互斥由租约仲裁层
  接管（`issue:N` 认领 + epoch fencing，见「租约仲裁」节），sync 收敛并发漂移。
- **链失败**：fix-issue.sh 非零退出 → trap 清 triaging/accepted/
  in-progress（枚举式，终态 rejected/needs-human 不清）→ issue 回零
  标签态，人工重投。例外 R4 熔断（exit 5，`breaker_tripped` 边）：
  熔断/门故障=机器无法继续需人工，链 exit 前落 needs-human——
  GitHub 侧可见，sync 无 PR 分支不清除 stray needs-human，解除走
  人工接管；dispatch 级熔断无具体 issue 可标，只在日志停摆。

派发器环境变量：`MAX_PARALLEL=4`、`FACTORY_MERGE_METHOD=merge`、
`INTERVAL=1800`、`GH_REPO=<owner/repo>`（无 github remote 时显式指定）。

## 租约仲裁（多写者化，2026-08-24）

单机时代互斥靠本地锁（`locks/dispatcher`）；多写者（多机/多租户）下本地锁
互不可见，"轮到谁"必须有唯一权威。三层架构：

- **仲裁** = `db/schema.sql`（Supabase/任何 Postgres，线性化）：claim /
  heartbeat / release / fence 全部服务端原子，epoch 每次易主 +1
  （fencing token）。迁移幂等：`psql "$SUPABASE_DB" -f .factory/db/schema.sql`。
- **投影** = GitHub labels + `state.py`：声明式收敛——标签只是事实的
  纯函数，sync 多写者安全（漂移自愈，见上节）。
- **围栏** = 出口围栏 + git refs 服务端保护：链副作用（label/评论）经出口
  （`issue_label_swap` / `issue_comment` / `issue_label`，PR#34 后全量覆盖）
  在发送前校验 epoch（`lease_guard`）——被夺/吊销的诈尸链在出口被拒；
  fence 校验与 GitHub 写之间的秒级残窗由回执幂等键
  （`factory:receipt:issue-N:rR`（批次 rbatch），`issue_comment` 查重跳过）兜底。

双态铁律：`SUPABASE_DB` 已设但 psql 不可达 = 配置错误，fail-closed 链终止
（exit 4），绝不降级——把配置错误伪装成单写者形态等于重新打开多写者竞态。
`SUPABASE_DB` 未设 = 显式选择单写者形态，降级本地锁（见下节「单写者降级」）。

链侧接线（fix-issue.sh）：打首个 issue 标签**前** claim `issue:N` → 后台
心跳（默认 60s，租期 900s 的 1/15 余量）→ 失约（被夺/吊销/过期）被 TERM，
`exit 143` 触发 EXIT trap 级联（台账/清标/worktree 回收/release）。同机
重投 = 续约（epoch 不变）；他机接管须等过期（epoch+1，旧链 fence 必失败）。
triage 批次无租约上下文（`LEASE_KEY` 未设出口不拦）：单 dispatcher 锁内
运行且只挑零标签 issue，与链的竞态窗口秒级可忽略。

### 单写者降级（SUPABASE_DB 未设）

未设 `SUPABASE_DB` = 显式选择单写者形态：claim / heartbeat / release /
fence 全部降级到本地锁文件（主树 `.factory/locks/leases/<key>.lock`，
worktree 经 git-common-dir 共享），无 PG 也能跑——下游复制工厂的最小形态。
语义对齐仲裁层：O_EXCL 判代、过期 = mtime+`FACTORY_LEASE_SECS`、过期可夺
（epoch+1）、fence 校验 machine-id+epoch、心跳刷 mtime、过期不许复活。
epoch 计数器（`<key>.epoch`）保证 fencing token 跨 release 单调不回零
（对齐 PG 行常驻语义）。一处刻意从严：持有中二次 claim 即便同机也拒——
本地锁的互斥对象就是同机进程，PG 的同机续约语义在此恰是要防的双链并发。
跨机互斥不存在（本地锁互不可见），每个降级路径 stderr 显式告警
single-writer mode。已设 `SUPABASE_DB` 但 psql 不可达不走此路径，
仍是 fail-closed（配置错误 ≠ 显式选择）。

### 租户 onboarding（运维手册，管理员执行）

```sql
create role "factory-<tenant>" login password '...';  -- 身份=连接串自证，客户端不可自报
grant factory_worker to "factory-<tenant>";           -- 仅 EXECUTE 四个 worker 函数，无表权限
insert into factory_tenants (tenant, rolname)
  values ('<tenant>', 'factory-<tenant>');            -- max_parallel 默认 2（配额=公平）
-- 机器免注册：首次 claim 自动登记 machine-id（观测标签；授权在 role 层）
```

### 应急 runbook（仅 postgres / supabase_admin）

```sql
select factory_revoke('<tenant>');                   -- 吊销租户：活跃租约立即过期 + epoch+1
select factory_machine_disable('<machine-id>');      -- 停用单机（精确止损：失控的是一台机器）
select key, machine_id, epoch, expires_at from factory_leases;   -- 现场盘点
select * from factory_events order by ts desc limit 20;          -- 审计追溯（claim/reclaim/release/revoke）
```

安全模型：RLS 全开且不建任何 policy（直表读写全拒）、worker 函数
SECURITY DEFINER、租户经 `session_user` 解析。详见 `db/schema.sql` 头注释。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `NODE_TIMEOUT` | `30m` | 单 AI 节点 `omp --max-time` 预算 |
| `SUPABASE_DB` | — | 仲裁层 PG 连接串（未设=单写者降级；已设不可达 fail-closed） |
| `FACTORY_LEASE_SECS` | `900` | 租期秒数（心跳间隔的 15 倍余量） |
| `FACTORY_HB_INTERVAL` | `60` | 心跳间隔秒数 |
| `FACTORY_RALPH_MAX` | `2` | implement↔review 修复轮上限（`0` = 单遍旧行为） |

## 门单独使用

```bash
# 周界锁（退出码 0=干净 1=触碰周界 2=门自身错误 fail-closed）
python3 .factory/guard.py --base origin/main [--head HEAD]   # PR 模式
python3 .factory/guard.py --files <path> [<path> ...]        # 列表模式
git diff --name-only base...head | python3 .factory/guard.py # stdin 模式

# 门灵敏度冒烟（退出码 0=全拦截 1=有 FAIL 2=配置错 3=还原失败 4=有 SKIP）
python3 .factory/mutations/run.py [--only G-01,G-03]
```

mutations 时序约束：**全绿证明必须在工作树干净时做**（相对 index 无
未提交修改）。target 处于人工编辑中时该缺陷 SKIP（防交叠护栏，设计
使然）——带 SKIP 的退出码 4「通过」不构成 auto-merge 依据，且容易被
误读为全绿。正确流程：提交/贮藏 → `run.py` 全绿（stamp 随之刷新）→
再依据证据推进。周界变更（factory-local.json 的 perimeter）后必跑：
stamp 指纹绑定会宣告旧证据过期（M4，设计 §11.3）。

## 并行测试门（ADR-016：段间 fan-out + 段内保守并行）

`factory-local.json` 可选键 `parallel_gate`——全量门禁的独立段并行执行。
缺键=未采用（零行为变化）；存在但损坏=fail-closed 报错（ADR-016）：

```json
"parallel_gate": {
  "workers": 0,
  "segments": [
    {"tag": "api", "argv": ["$PY", "-m", "pytest", "tests/", "-q"]},
    {"tag": "lint", "shell": "\"$1\" scripts/lint.sh | tail -5"},
    {"tag": "java", "argv": ["mvn", "test"], "intra": "auto", "stack": "maven"}
  ]
}
```

- `workers`：0=不限并发（缺省），>0=并发上限；段缺省 cwd=仓库根
- argv 的 `$PY` 词执行期替换为解释器（env PYTHON 或 python3）；shell 段
  以 `bash -o pipefail` 执行、`$1`=解释器（管道真码透传）
- 失败语义：不短路，全段跑完统一裁决；失败段日志保留（独立临时目录 +
  回放 stdout），成功即整体清理
- 段内并行 `intra:"auto"` 逐段 opt-in，只注保守档参数（模块/fork/worker
  级分发）：pytest `-n auto`（需 xdist）、maven `-T 1C -DforkCount=1C
  -DreuseForks=true`、gradle `--parallel`、jest `--maxWorkers=50%`；
  vitest/go/cargo 默认已并行零附加；phpunit/dotnet 保持串行。顺序敏感
  段不设 intra（缺省 off）

三种用法：

```bash
# A. 门禁直连（final_gate_cmd 直指编排器，零宿主胶水）
python3 .factory/factory_lib.py parallel-gate

# B. 宿主脚本组合（run_tests.sh 模式）：回收失败 tag → 串行尾段 → 统一裁决
python3 .factory/factory_lib.py parallel-gate --failed-tags "$FAILED_TAGS"
while IFS= read -r t; do FAILED+=("$t"); done < "$FAILED_TAGS"

# C. 本地提速：手动跑，失败清单落盘自取
python3 .factory/factory_lib.py parallel-gate --failed-tags /tmp/failed.txt
```

退出码：0=全绿，1=有失败段，2=门自身错误（fail-closed）。

> 注：本节及「集中巡检」（B1/B2）为上游真相源视角，机制参考；
> 本仓是下游，操作面是上文的 sync 命令与「反哺上游」节。

## 移植到其他仓库（ADR-009 后：一份配置 + 两条命令）

本地化已全部数据化到 `factory-local.json`（M4 + ADR-009），链脚本与
prompts 零宿主专名（gauntlet `factory-portability` 门机械化盯防）。
移植（如 etf-radar）只需：

1. **拷贝** `DISTRIBUTION.json` 的 full 面 + `prompts/` + `tests/` 到目标
   仓库 `.factory/`（排除 artifacts/locks/worktrees 等运行时产物）。
2. **写目标仓的 `factory-local.json`**：perimeter（目标仓治理/发布面路径）、
   reject_guidance（锚定目标仓 MISSION 判据措辞）、repo_identity /
   reading_scopes / review_basis / final_gate_cmd（目标仓真实测试命令，如
   `uv run pytest`）/ pr_review_skills / upstream_repo / upstream_path /
   feedback_branch_prefix。
3. **写目标仓的 `MISSION.md`**（使命与 triage 判据），然后**重跑
   `mutations/run.py`** 重新证明 kill rate——改过周界未重证的门不算门
   （evidence-stamp 指纹绑定会强制）。
4. **平台适配（GitHub 仓可跳过）**：目标仓若托管在云效 Codeup，设
   `FACTORY_HOSTING=codeup` + `YUNXIAO_ACCESS_TOKEN` + `CODEUP_ORG_ID` +
   `CODEUP_REPO_ID`（或 `CODEUP_REPO_PATH`），见 ADR-008——Codeup 工作项
   面已实装（#67）、MR 面缺口 (b)(c) 由评论标记模型承载（#66：add 标记
   评论/置 resolved 手势，ADR-008 附记），全链状态机可跑（issue 全套需
   `CODEUP_SPACE_ID`/`WORKITEM_TYPE_ID`/`ASSIGN_USER_ID`）；
   GitHub 仓零配置（hosting 默认走 gh，行为不变）。

历史：ADR-009 前的「改五处 + 次级审计 prompts 仓库引用」已由数据化
消灭——triage/prime/review 的仓库身份、阅读范围、审查依据、final_gate
示例现在全部经 `factory_lib.py repo-vars` 运行时注入。

## 上游同步（移植后的增量维护）

本仓是 `.factory` 工具链的唯一真相源（`DISTRIBUTION.json` 分类）；
下游仓（etf-radar 等）用 `sync-from-upstream.sh` 追增量，不再手工 diff 对账：

```bash
# 漂移检查（full 面漂移 exit 1，可挂 CI/gauntlet；local 面只报告）
.factory/sync-from-upstream.sh <upstream-path> --check

# 追平：full 文件直接覆盖 + 锚点写 upstream-lock.json；local 只给 diff 摘要
.factory/sync-from-upstream.sh <upstream-path> --apply

# 中心驱动（B1，ADR-011）：任意 cwd 操作目标仓；--commit 追平+锚点+blame-ignore
# 以单提交落库（不推送）；目标仓 .factory 脏则拒绝
.factory/sync-from-upstream.sh <upstream-path> --repo <repo-path> --apply --commit
```

三态语义：**full**（零本地化，blob 直接覆盖，漂移=门禁失败；ADR-009 后
含全部链脚本、feedback-upstream、omp-isolated.yml、db/schema.sql 与 tests/）；
**local**（ADR-009 后**已归零**——历史 local 面 guard.py/factory_lib.py/
feedback-upstream.sh/tests/ 均数据化升 full，漂移的正道是
`feedback-upstream.sh` 反哺后追平，不是静默分叉）；
**skip**（仓特定/运行时产物：MISSION/factory-local.json/mutations 等）。
上游可为 bare 仓（经 git 对象库读）。

漂移闭环：下游热修 → feedback-upstream 反哺 PR → 上游合并 → 下游
`--apply` 追平 → `--check` 归零。双向都有机器检查，分叉不再靠人工记忆。

同步成熟度路线（M1–M4，完整设计见
`docs/design/factory-harness-design.md` §11；M 编号与 Five Levels 的
L4 无关）：

- **M1 ✅** 三态清单 + sync 脚本 + 锚点（本节）。
- **M2** dispatch 轮末自动 `--check`：full 漂移走确定性 PR 流
  （apply → gauntlet → factory/sync-<锚点> 分支 → needs-review 人工
  合并；**不走 fix-issue 链**——guard PERIMETER 含 .factory/，链按
  设计拦工具链自变更）；local 漂移落 needs-human issue；apply 后
  当轮即止（自我指涉护栏）。
- **M3** 上游 merge 发 repository_dispatch，下游分钟级触发 M2。
- **M4 ✅ + ADR-009** 本地化外置 `factory-local.json`（perimeter/判据
  措辞/门命令/仓库参数/上游指针全成数据），guard.py/factory_lib.py/
  feedback-upstream.sh/tests/ 从 local → full，**local 面归零**；PERIMETER
  blob 指纹绑定 EVIDENCE——改配置未重证 kill rate 即非绿。

### 集中巡检与 blame-ignore（B 阶段，ADR-011）

追平提交是机械动作，但 `git blame` 眼里与人工改动无异；且逐仓手工
`--apply` 发现漂移滞后。B 阶段两件套：

- **B1 `--repo` + `--commit`**（`sync-from-upstream.sh`）：中心驱动、
  任意 cwd 操作目标仓；追平产物+锚点+blame-ignore 以单提交落库
  （`factory: 上游同步追平（<sha9>）`），落当前分支**不推送**。
  目标仓 `.factory` 有未提交 tracked 改动时拒绝（fail-closed，
  热修不被自动提交淹没）。blame-ignore **滞后一条**：提交无法含
  自身 SHA，本轮记上一轮追平提交；并 `git config blame.ignoreRevsFile`
  指绝对路径（相对路径在子目录 blame 下 rc128）。存量历史追平提交
  一次性回填（一行一个 40-hex 全 SHA，`#` 开头为注释）：
  ```bash
  git log --grep='追平' --format=%H | sort -u >> .git-blame-ignore-revs
  ```
- **B2 `downstream-check.sh` + `downstream.local.json`**（真实清单，gitignored，ADR-012）：中心仓单点巡检
  全舰队（清单 skip 分发——中心专属状态，下游不携带、缺失
  fail-closed 即正确边界）；`--apply-commit` 对漂移仓跑中心版 sync
  单提交追平。巡检一律 `--anchor main`（中心发布线）且执行**中心版**
  脚本——下游副本可能滞后，鸡生蛋。漂移即 osascript 通知
  （`FACTORY_NO_NOTIFY=1` 关断）；shlock 互斥；单仓失败记 `[错误]`
  继续不中断。

C 阶段（中心经 worktree 直接操作下游仓 + CI composite action）另案推进。

### 下游采纳 M2/M4 checklist（顺序不可倒）

前置：本仓已按「移植到其他仓库」完成首次移植（MISSION/PERIMETER/
测试门四步）。此后增量采纳：

1. **拉新版 full 面**（含数据化后的 guard.py / factory_lib.py /
   upstream-sync-check.sh）：
   ```bash
   .factory/sync-from-upstream.sh <awesome-rules 路径> --apply
   ```
   此时 guard 会因缺 factory-local.json fail-closed（exit 2）——
   这是正确行为，继续下一步。
2. **建本仓的 factory-local.json**（skip 分发，每仓一份）：
   `perimeter` 从本仓 MISSION.md「周界（PERIMETER）」逐条誊抄
   （guard.self_check 每次运行强制核对一致性——两边不一致 = exit 2）；
   `reject_guidance` a/b/c 措辞按本仓 MISSION 判据本地化。
3. **验证配置**：`python3 .factory/guard.py --files <任意文件>` 退出码
   正常（0 或 1，非 2）；gauntlet（若有）factory-local-validity 层绿。
4. **重证 kill rate（关键，不可跳）**：工作树干净时跑
   `python3 .factory/mutations/run.py` 全绿——stamp（evidence-stamp.json）
   随之绑定本仓周界指纹；此后改 factory-local.json 未重证 = 启动即宣告
   证据过期。defects.json 锚点若因仓差异失效（如目标文件行文不同），
   本地化锚点后重跑。
5. **启用 M2**：`.factory/upstream-lock.json` 写入
   `{"upstream": "<awesome-rules 路径>"}`（或 dispatch 环境设
   `FACTORY_UPSTREAM`）；下一轮 dispatch 轮末自动生效——full 漂移开
   needs-review PR（人工合并）、local 漂移落 needs-human issue、
   无 gh 凭据降级为日志报告。

顺序不可倒的原因：先改配置后拉脚本（步骤 2 先于 1）会让旧 guard 读到
它不认识的配置静默放行；先启用 M2 后建配置（步骤 5 先于 2）会让每轮
dispatch 在 fail-closed 上空转。

## S1/S2 已知边界

- S1 手动跑 `fix-issue.sh`；S2 用 `dispatch.sh`（本仓库现已内置）。
  标签状态机唯一权威在 `state.py TRANSITIONS`（转移表全覆盖有测试，
  meta-test 强制每条边有场景 fixture）。
- S1→L3 出口判据「行为破坏类缺陷集扩充后 kill rate ≥80%」已证（2026-08-26 重证）：
  篡改类 7/7 + 行为破坏类 5/5，kill rate 12/12 = 100%，负例放行 3/3；
  证据口径与逐条击杀明细见 `.factory/mutations/EVIDENCE-2026-08-26.md`。
  A5 仍为必要非充分条件——`metrics/auto-merge-unlocked` 的开启/重签是治理
  动作，由人类决定（2026-08-26 已重签至 12/12 口径）。
- holdout 输入白名单是提示词纪律级约束，S2+ 换 SDK
  `restrictToolNames` 物理化（设计文档 §7）。
- `--fill` 生成的 PR 标题质量依赖 implement 的 commit 信息。
- needs-fix 重派复用 `fix-issue.sh`（`worktree add -B` 重置既有分支），
  全节点重跑；链内断点续跑（resume）未实现。

## 多会话并行协议（worktree 隔离 + 分支约定）

工厂链在独立 worktree（`${仓库}/.factory/worktrees/issue-N`，fix-issue.sh
`worktree add -B`）跑，人工侧工作树不受链的 checkout/commit 影响。但 worktree
共享 refs 与 git config——它隔离文件层，不隔离历史层。硬边界约定：

- **专属分支**：每个 worktree/会话一个专属分支提交（工厂链分支
  `factory/issue-N`，worktree 空闲驻留 `factory/base`）；链基线取
  `github/main`（fetch 后），不依赖人工侧本地 main 的更新时序。
- **main 服务端保护**（唯一硬执行点）：require PR、禁 force push、
  禁删除；直推 main 一律被拒。链 auto-merge 用 `--admin` 合并。
  本地 git 无权限模型——任何本地约定对失控会话无执行力，服务端才有。
- **历史重写后盘点孤儿**：任何 force push / 分支重置 / 快照压缩之后，
  立即 `git fsck --lost-found` 列出全部失联提交对象，逐个鉴定
  （`git show <sha> --stat`：真实工作 / 已被吸收 / 破坏 / 过时变体），
  真实工作以文件级 patch 恢复走 PR，确认无价值才允许丢弃——失联 ≠
  丢失，对象在 gc（默认两周）前都可救。
- **单写者推定**：人工侧会话不要跑 `.factory/` 脚本（watch 常驻实例
  互斥靠主树 `.factory/locks/dispatcher`，但 git 写入无互斥）。
- **调度形态（2026-08-22 断档教训）**：本仓经 `~/.config/factory` hub
  （LaunchAgent 600s）kick `cron-dispatch.sh` 单轮；`--watch` 常驻无
  launchd 监管（崩了无人拉起、重启不自启），98bdabbc 删包装器换 watch
  后断档 13h——勿再单用 watch 形态。

## 反哺上游（awesome-rules）

本工厂移植自 awesome-rules，两侧各自演化。反哺 = 把本仓对工厂的**可泛化**
改进以 PR 形式推回上游，人工合并；上游漂移只报告不自动吸收。

```bash
bash .factory/feedback-upstream.sh --dry-run   # 只看候选 + 漂移报告，零副作用
bash .factory/feedback-upstream.sh             # 完整管线：pick→AI适配→上游门禁→PR
```

- **候选标记**：可泛化的工厂提交在 commit message 尾部加
  `Upstream-Feedback: yes` trailer（判断在提交时做出）。
- **管线**：clean cherry-pick 由脚本完成（保真）；conflicted 与特化剥离交
  omp 适配节点（`prompts/feedback-adapt.md`）；上游门禁绿才开 PR，红只收
  报告。一候选一提交，只允许动 `.factory/`。
- **账本**：`.factory/feedback-log.jsonl`（append-only）记录已反哺 SHA 与
  上游 PR 号，防重复反哺。
- env：`UPSTREAM_PATH`（默认 `~/sources/awesome-rules`）、
  `UPSTREAM_REPO`、`NODE_TIMEOUT`。

## 移植记录（awesome-rules → etf-radar，2026-08-21；2026-09-27 追平）

首次移植四步 + 后续追平：

1. **MISSION.md**：重写为 etf-radar 使命（数据流水线/前端/测试/文档维护），
   周界覆盖治理面（CLAUDE.md/CONVENTIONS）、质检线（.factory/scripts/
   .githooks/.github）、数据面（data/config/supabase）、依赖与发布面。
2. **本地化配置**：ADR-009 后周界/判据措辞/门命令/上游指针全部数据化到
   `factory-local.json`（skip 分发，每仓一份）；guard.py 从中载入 perimeter，
   MISSION.md 仍是唯一真相源（self_check 每次运行核对）。
3. **测试门**：`scripts/run_tests.sh`（mypy strict + ruff + pytest --cov +
   diff-cover / tsc -b + eslint + vitest --coverage，与 pre-push、CI 同口径），
   `--evidence backend|frontend` 证据段模式（holdout 证据源）；2026-09-27
   起 backend/frontend 两段经并行门 fan-out。mutations kill rate 已在本仓
   重证：6/6 拦截 + 1/1 负例放行（evidence-stamp 周界指纹绑定）。
4. **增量维护**：`sync-from-upstream.sh --apply` 追平 full 面（本文档头部
   锚点）；仓特定缺口（如本仓已采用的 sourcery 闸）手工补。

## S1/S2 已知边界

- S1 手动跑 `fix-issue.sh`；S2 走 hub 派发（见「本仓定制」）。
  auto-merge 默认关闭（A5 门控：`FACTORY_AUTO_MERGE=1` +
  `metrics/auto-merge-unlocked` 双条件）。标签状态机唯一权威在
  `state.py TRANSITIONS`（每条边全覆盖有测试）。
- holdout 输入白名单是提示词纪律级约束（`omp-isolated.yml` 物理隔离
  triage/holdout 节点的 advisor）。
- `--fill` 生成的 PR 标题质量依赖 implement 的 commit 信息。
- needs-fix 重派复用 `fix-issue.sh`，全节点重跑；链内断点续跑未实现。
- **main 无分支保护**（实测可直推）：auto-merge 与直推安全完全依赖门禁
  与人工自律；如需服务端硬执行点须另开 branch protection（上游有、本仓无）。

## 多会话并行协议（worktree 隔离 + 分支约定）

工厂链在独立 worktree（`.factory/worktrees/issue-N/`）跑，人工侧工作树
不受链的 checkout/commit 影响；deps 共享（UV_PROJECT_ENVIRONMENT 指主
venv + node_modules 软链，周界保证依赖锁一致）。worktree 共享 refs 与
git config——它隔离文件层，不隔离历史层。硬边界约定：

- **专属分支**：每个 worktree/会话一个专属分支提交（工厂链分支
  `factory/issue-N`）；链基线取 `origin/main`（fetch 后），不依赖人工侧
  本地 main 的更新时序。
- **历史重写后盘点孤儿**：任何 force push / 分支重置之后，立即
  `git fsck --lost-found` 列出失联提交对象逐个鉴定，真实工作以文件级
  patch 恢复走 PR——失联 ≠ 丢失，gc（默认两周）前都可救。
- **单写者推定**：人工侧会话不跑 `.factory/` 脚本；hub 是唯一常驻派发
  者（仓库侧 shlock + dispatcher 锁互斥）。
