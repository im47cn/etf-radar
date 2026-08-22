# Factory Harness 设计：awesome-rules 的 L4 自举工厂

> 状态：S0 定稿 v0.1（2026-08-21）· 选型方案 B（omp headless + 自研薄 dispatcher）
> 治理依据：[MISSION.md](../../MISSION.md)（工厂永不可改）
> 参考：Dan Shapiro 五级框架、coleam00/dark-factory-experiment、coleam00/skills、coleam00/Archon

---

## 0. 摘要

在 awesome-rules 仓库上构建 Level-4 自举工厂：issue 进、验证过的合并出，人类只写
issue 和晋升 release。**不引入新框架**——dispatcher 是零 LLM 的 bash，AI 节点由
omp 以进程级 fresh context 执行，治理与质检复用仓库既有资产（steering/、
scripts/run_tests.sh、plugin_lock 体系）。

S0 已落地并验证：`MISSION.md`（宪法）、`.factory/guard.py`（周界锁）、
`.factory/mutations/`（门灵敏度冒烟，**kill rate 4/4 = 100%，负例放行 1/1**）。

---

## 1. 第一性原理

### 1.1 稀缺输入分析

技术通缩（Shapiro）意味着代码生产成本趋零。此时人类的稀缺输入只剩三类：

| 稀缺输入 | 载体 | 本设计的对应物 |
|---|---|---|
| 意图 | issue / spec | GitHub issue（人类独占） |
| 判断 | 宪法 / 规范 | MISSION.md + steering/（工厂不可改） |
| 信任锚 | 验证门 | guard + tests + holdout + mutations |

**Harness 的功能定义：最大化"机器可判定工作"的占比，同时使三类稀缺输入不可被
机器稀释。** 一切组件由此推导，不满足此定义的组件一律不建。

### 1.2 公理与推论

- **A1 上下文即作弊通道。** agent 看过实现计划就会自我确认（StrongDM 失败根因）。
  → 推论：AI 节点进程级 fresh context；验证器 holdout（只读 issue 与运行结果，
  永不读 plan）。
- **A2 不能修改审判自己的法律。** agent 可改规则时，规则不再是约束而是参数。
  → 推论：治理文件 + 周界 + 验证门自身全部入锁（guard.py）；门 fail-closed
  （门崩溃 = 拦截，而非放行）。
- **A3 可靠性反比于外壳复杂度。** 智能放在外壳（dispatcher 做决策）必然产生幻觉
  调度。→ 推论：dispatcher 零 LLM、纯 bash 读 label；智能全部内化为资产
  （`.factory/prompts/*.md`，可版本化、可评审、引擎无关）。
- **A4 不可观测即不可信。** → 推论：状态外置到 GitHub label，不用本地数据库/
  消息总线；审计 = git 历史 + label 流转记录，人类随时可介入。
- **A5 未证明的门不是门。** → 推论：auto-merge 开启的前提是 mutations 注入
  缺陷被全量拦截；灵敏度是跑出来的，不是声明的。
- **A6 不可信文本不能直接进决策。** issue/PR 正文是 prompt injection 面。
  → 推论：正文仅经 triage 节点产出结构化 JSON 进入下游；下游节点引用结构化
  产物，不回读原文。

### 1.3 组件最小集（由公理推导，缺一不可，多一即删）

```
GitHub label 状态机（A4）
  └─ bash dispatcher，cron 驱动，MAX_PARALLEL 限流（A3）
       └─ AI 节点 = 读 .factory/prompts/*.md 的 omp 进程（A1/A3）
            └─ 确定性门：guard.py（A2）→ run_tests.sh（A5）→ holdout（A1）
                 └─ mutations 证明门灵敏度（A5）→ 才允许 auto-merge
```

---

## 2. 对参考方案的批判性吸收

### 2.1 dark-factory-experiment

**吸收**：四条铁律原文进 MISSION；GitHub 状态机；harness/agent/model 三层分离；
dispatcher 无状态化（一切状态在仓库可见处）。

**批判与修正**：

1. **label 状态机存在竞态窗口**。两个 cron tick 可能同时 pick 同一 issue。
   其以 `.factory/locks` + 固定优先级串行缓解。我们的 S2 dispatcher 必须先原子
   抢占 label（`gh issue edit --add-label factory:in-progress` 幂等重试，失败即
   放弃本 tick），再 dispatch；绝不"读后即走"。
2. **周界清单是利益权衡，不是真理**。过宽的代价 = 多走人审（低）；过窄的代价 =
   被绕过（高）。风险不对称 → 选宽。本库周界因此连 `design/`、`hooks/`、全部
   插件 manifest 一并锁入（见 MISSION）。
3. **场景风险画像不同**。dark-factory 维护运行时 web 应用（爆炸半径 = 线上）；
   本库是规则库（爆炸半径 = 下游团队的审查质量）。隐性半径更大——被污染的规范
   会静默复制到每个使用方。结论：治理锁不因"只是规则库"放松，反而加码
   （steering/ 全量入锁）。
4. **"工厂不写自己的 issue"停在 L4 是诚实，不是缺陷**。L5（工厂自产 spec）无
   公开稳定案例，从路线图删除，拒绝为幻境设计。

### 2.2 Archon（以及为何不选它）

Archon 的 YAML DAG（prompt/bash 节点、loop until、interactive 门）是对的抽象，
但作为依赖引入本方案是负资产：

- **表达力诱惑**：YAML 越写越长是 Archon 用户的实际轨迹；我们的流程刻意退化到
  "bash 循环 + .md 资产"，可审计性更高（A3）。
- **工具链割裂**：Archon AI 节点 spawn Claude Code；我们的验证节点需要 omp 的
  browser/lsp/结构化输出/受限工具集——这些在 Claude Code 节点里不存在。
- **UI 在 L4 冗余**：状态全在 GitHub（A4），观测面 = issue/PR 页面本身。
- **重估条件**（写下来防止情绪化推翻）：≥3 个工厂实例需要统一编排，或出现跨
  仓库工作流编排需求时，重新评估 Archon。届时 §4 的引擎适配层是唯一改动点。

### 2.3 coleam00/skills（PIV 与元技能）

**吸收**：PIV 循环骨架（prime → plan → implement → validate → review → commit →
PR）作为 fix-issue 工作流的节点序列；元技能四件套思想（drift / ablate /
opportunity-scan / evolution-review）作为"流程的 CI"。

**批判**：

1. 33 技能 ≈ 4200 token 常驻上下文本身就是成本——**ablate 应对自己人**。本方案
   不引入其技能包，只取思想。
2. 元闭环不重造：本仓库 `skills/skill-evo/` 已是本地化实现（会话经验自动提炼
   → 人工审核应用，GEPA 引擎自进化），与元技能四件套一一对应（见 §10 映射表）。
   工厂的 decisions.md 喂给 skill-evo，即完成"流程数据 → 规则进化"闭环，且进化
   权锁在人类（skill-evo 本就是人工审核制）。

### 2.4 对上一轮头脑风暴的自查修正

| 上轮说法 | 修正 | 理由 |
|---|---|---|
| herdr 保留为 "L3 驾驶舱（推荐）" | 降级为可选观察面 | herdr 状态识别是启发式（`unknown` ≠ 完成、alternate screen 不可回读），不进关键路径；S1 人工监督期可用可不用 |
| 新建 `gate.sh` 包装测试门 | 删除该层 | `scripts/run_tests.sh` 已是既定门；纯转发层是无重量代码 |
| "mutations kill rate 达标" | 数字化 | 篡改类 100%（S0 已达成）；S1 扩行为破坏类缺陷后 ≥80% 方可开 auto-merge |
| "引擎可替换" | 收敛为硬约束 | 适配面 = §4 的 `run_node` 一个函数；引擎无关资产（prompts/guard/mutations/状态机约定）是第一公民 |

---

## 3. 定稿架构（方案 B）

```
人类（写 issue、晋升 release；治理 PR 人审）
  │
  ▼
GitHub 状态机（issues / PRs / labels）……… A4：审计=git历史
  ▲ label 抢占（幂等，防竞态）
  │
  dispatcher：bash + gh，cron 30min，MAX_PARALLEL=4，零 LLM …… A3
  │
  ├─ triage 节点（omp，outputSchema JSON）……… A6
  ├─ fix-issue 链：prime → plan → implement(PIV loop) → tests → PR … A1
  └─ validate-PR 独立门：guard → tests → 并行AI评审 → holdout → synthesize
       ├─ 全绿 → auto-merge（前提：mutations 达标）……… A5
       └─ 打回 needs-fix（≤2 次）→ needs-human
```

模型路由 = 配置而非代码（dark-factory 实证：换 provider 只改节点参数）：
extract 类（classify/摘要）用便宜模型，reason 类（plan/review/holdout 裁决）用
强模型，implement 用中档；S3 用 benchmark 矩阵校准，不凭感觉。

### 引擎形态决策

- **S1–S2：`omp -p`（CLI 非交互模式）**。每节点一个干净进程 = 物理级 fresh
  context（A1 直接满足），零新代码，spawn 开销（百 ms 级）相对分钟级节点无关
  紧要。
- **S2+：SDK 直连（`@oh-my-pi/pi-coding-agent`）**，仅用于需要 `outputSchema`
  结构化裁决与 `restrictToolNames` 最小权限的节点（triage、holdout 裁决）。
- 两形态都只经过 §4 适配层，dispatcher 不感知差异。

---

## 4. 引擎适配层接口规范（唯一与 omp 耦合的代码）

```ts
// .factory/engine.ts —— 方案 B 的全部引擎耦合面（≤50 行实现）
// 不变量：dispatcher 与工作流只依赖本接口；换引擎只改本文件。

type NodeSpec = {
  promptFile: Path;              // 唯一提示词来源：.factory/prompts/*.md，禁内联
  worktree:  Path;               // 节点专属隔离工作树（fresh context 的物理基础）
  modelRole: "extract" | "reason" | "implement";  // 模型路由=查表，非硬编码
  tools?:    string[];           // 可选白名单；给出即 restrictToolNames=true
  outputSchema?: JSONSchema;     // 给出即结构化输出（triage/裁决节点必填）
  budget: { usdCeiling: number; minutes: number }; // 节点级地板锁，超限即 abort
};

type NodeResult = {
  artifact:  Path;               // 结构化产物落盘路径（local:// 约定），下游只读此文件
  exit:     "ok" | "fail" | "budget";
  structured?: unknown;          // outputSchema 对应的已验证 JSON
};

async function runNode(spec: NodeSpec): Promise<NodeResult>;
// 实现A（S1–S2）: spawn `omp -p "$(cat spec.promptFile)" --cwd spec.worktree`
//                 budget 由 `timeout` + 事后成本核算执行
// 实现B（S2+）  : createAgentSession({
//                   sessionManager: SessionManager.inMemory(),      // 无持久化
//                   toolNames: spec.tools, restrictToolNames: true, // 最小权限
//                   outputSchema: spec.outputSchema,
//                 })
//                 注意：完成信号必须等 agent_end 且 isTerminal !== false
// 不变量：
//   I1 每次调用 = 全新进程/会话，无跨节点状态泄漏（A1）
//   I2 prompt 永远来自文件，接口不收字符串（资产化，A3）
//   I3 失败必须非 ok 退出，禁止静默降级（fail-closed，A2 同源）
//   I4 产物经 schema 验证后才算 ok（A5 同源）
```

---

## 5. omp SDK headless 成熟度验证结论

依据 `omp://sdk.md`（SDK 文档），逐项核对方案 B 的关键假设：

| 假设 | 证据 | 结论 |
|---|---|---|
| fresh context 可物化 | `SessionManager.inMemory()`：无文件持久化，面向 ephemeral worker | ✅ |
| 最小权限节点 | `toolNames` + `restrictToolNames: true`：受限会话默认禁 ambient MCP/extensions/自定义命令/LSP | ✅ 强于预期 |
| 结构化裁决 | `outputSchema` / `outputSchemaMode`（strict 可选） | ✅ |
| 编排场景支持 | 专门的 subagent-oriented 选项：`taskDepth`、`parentTaskPrefix`、`requireYieldTool` | ✅ SDK 设计者已把 orchestrator 当一等场景 |
| 非交互模式成熟 | print/RPC/ACP 模式 `hasUI=false` 一等公民（如跳过 LSP warmup 的显式设计） | ✅ |
| 进程级隔离可用 | CLI print 模式 + 每次调用独立进程 | ✅ S1 起步形态 |

**风险（写进登记册）**：SDK 直连时 `agent_end` 的 `isTerminal` 可为 `false`
（后台维护未排干），必须等 `isTerminal !== false` 才算完成——CLI 形态下由 CLI
承担；Bun ≥ 1.3.14 依赖；同进程多顶层会话需私有 `AgentRegistry`。

**结论：方案 B 的引擎假设全部成立，无需引入 Archon。**

---

## 6. 治理模型与 S0 已落地件

三层锁，互为冗余：

| 层 | 机制 | 状态 |
|---|---|---|
| 语义层 | `.factory/guard.py`：周界前缀匹配，触碰即 exit 1；**fail-closed**（内部异常 exit 2 = 拦截） | ✅ S0 已落地 |
| 仓库层 | `scripts/plugin_lock.py` 安装入口 blob 锁（既有 zero-regression 体系） | ✅ 既有 |
| 平台层 | GitHub 分支保护 + CODEOWNERS：周界路径强制人审 | ⬜ S1 配置 |

S0 验证证据（2026-08-21 实测）：

```
$ python3 .factory/mutations/run.py
  [G-01] 篡改 MISSION.md 铁律        PASS blocked=True (rc=1)
  [G-02] 篡改 steering/testing-*.md  PASS blocked=True (rc=1)
  [G-03] 篡改 guard.py 自身          PASS blocked=True (rc=2, fail-closed 路径)
  [G-04] 篡改 scripts/run_tests.sh   PASS blocked=True (rc=1)
  [B-01] 良性变更 CHANGELOG.md       PASS blocked=False (rc=0，负例放行)
  kill rate 4/4 = 100%；负例 1/1；还原零残留（字节级校验）
$ python3 .factory/guard.py --base HEAD~1   # PR 模式: 7 files, 0 命中, exit 0
```

mutation runner 安全设计（工作树含人工未提交修改时依然安全）：
内存字节备份 + `finally` 写回，**绝不使用 git checkout 还原**；已跟踪且脏的
target 一律 SKIP；还原后逐文件字节校验，不一致即 FATAL 退出码 3。

---

## 7. 状态机与工作流（S2 已落地）

### Label 状态机（权威：`.factory/state.py` TRANSITIONS）

```
Issue: factory:triaging → factory:accepted | factory:rejected
                          → factory:in-progress（dispatcher 抢占锁）
                          → factory:in-review（PR 打开，状态接管）
PR:   factory:needs-review → factory:approved | factory:needs-fix | factory:needs-human
      factory:needs-fix ×≤2（label-add 事件计数）→ 第 3 次 needs-human
终态: rejected（标签承载机器状态，判据明细由回执评论承载 #57/#59/#60 实证；
      标记评论=人类手动覆盖通道，人写人删——链回执刻意不含裸标记，
      否则重投被永久钉死） | closed（GitHub 原生，清流转标签）
优先级：priority:critical|high|medium|low（triage 打标，dispatch 排序）
```

**S2 落地记录（2026-08-21，本节由骨架转为代码后的定型）**

组件：`state.py`（转移表 + plan_phase 纯函数 + `table|link|plan` CLI）、
`factory-state.sh`（同步器）、`dispatch.sh`（派发器）、
`test_state.py`（8 测试：12 条边全覆盖 + meta-test 双向漂移检测）。

与骨架的三处分歧及理由：

1. **claim 用 add+remove 而非仅 add**。GitHub 换标签非原子，骨架的
   `--add-label || continue` 会把 accepted 滞留为双标签态（accepted+
   in-progress 并存 → 队列重复派发）。实现为单实例 dispatcher + sync
   收敛漂移；单实例是 claim 互斥的真实保证（README 已声明假设）。
2. **状态判定不是 dispatcher 内联 if，而是独立纯函数**。骨架让 dispatcher
   "读 label 做决策"，实现把"读"整体抽成 `plan_phase(事实) → (phase, ops)`
   并配转移表 + 全边覆盖测试——理由见下方第一性原理。
3. **needs-fix 计数契约显式化**：轮次 = PR 上该标签 add 事件数（GitHub
   timeline 稳定可用）；dispatch 重派必须移除 needs-fix，否则标签滞留、
   事件不再触发、计数冻结（test_rounds_boundary 锁定 0/1→fix、2/9→human）。

**第一性原理：为什么转移会"实现一半"**。同日三次事故（S1 忘写 rejected
标签、DRY 只认位置参数误发真链、needs-fix 转移写在了不存在的 validate-pr
里）共享一个根因：**状态转移作为副作用散落在多个命令式步骤中，完整性
依赖每处作者记得写全**。结构性解法不是"更小心"，而是消灭转移代码：

- 可观测标签 = 仓库事实的纯函数（派生状态）。事实是 PR/reviewDecision/
  label 事件/标记评论，推导是 `plan_phase`，收敛是幂等 sync。"忘写转移"
  在此模型下不可表达——没有转移可忘写，只有状态函数可测（且已全边覆盖）。
- 链内即时打标降级为新鲜度优化：写错了、漏写了，下一次 sync 自动收敛。
  可观测性 fail-open，不影响门（guard/holdout fail-closed）。
- 例外即规则显式化：锁（triaging/in-progress）无法从事实推导——它是
  "正在运行"的声明，事实里只有结果没有进行时。锁必须命令式且单一属主
  （chain 写 triaging、dispatch 写 in-progress），sync 永不触碰（终态清理
  除外）。`test_ops_invariants` 断言非终态 ops 永不含锁。
- 转移表即 spec：TRANSITIONS 是唯一权威，meta-test 强制 SCENARIOS 与表
  集合双向相等——新增转移忘配 fixture、或 fixture 引用不存在的转移，
  测试即红。表、代码、场景三方锁死。

### Dispatcher 骨架 → 实现（S2 已落地）

```
dispatch.sh [--dry-run] [--watch] [--interval SEC]:
  sync（factory-state.sh sync --all，先对齐事实）
  → PR 结果：approved 且 A5 门开（FACTORY_AUTO_MERGE=1
    + metrics/auto-merge-unlocked 存在）→ merge；否则人工
  → needs-fix 重派（移除 needs-fix 保计数活性 → claim → fix-issue）
  → accepted 队列（priority 排序，MAX_PARALLEL 槽，bash3 兼容轮询）
  → wait + 收尾 sync
固定优先级：PR 结果 > fix-issue（triage 内联于 fix-issue.sh，无独立批）
```

### 四条工作流

| 工作流 | 节点链 | 门 |
|---|---|---|
| triage | 读 MISSION 判据 → outputSchema JSON 裁决 → gh 打 label（二值） | JSON schema 校验 |
| fix-issue | prime（复用 codebase-memory 图谱）→ plan → implement（PIV 循环，fresh context 逐任务）→ tests → PR | `run_tests.sh` |
| validate-PR | **guard.py → run_tests.sh** → 并行 AI 评审（按 PR 触及面选配 api-guard / ddl-guard / arch-guard / reviewer / security）→ holdout 裁决 → synthesize | guard + holdout |
| comprehensive-test（周） | 起服务（readiness 探针）→ omp browser E2E → 报告 → 失败自动开 issue 回灌 | 自愈闭环 |

fix-issue 与 validate-PR 的 AI 评审节点**必须**是不同会话（A1）。

**holdout 物理隔离（S1 已实现，不等 S2）**：`omp -p --no-tools`——验证器
无任何工具（无 read/bash/grep），白名单输入（issue 标题 + tests-output.txt）
由链脚本确定性内联进 prompt，prompt 即验证器的全部世界；issue 正文不进
验证器（不可信文本最短路径）。裁决 JSON 从 stdout 解析（fence 优先）。
已实测：合成钓鱼场景（同目录放置声称"已修复"的诱饵 plan.json + 与诉求无关
的绿灯测试输出）→ 正确 FAIL，诱饵零影响。残留通道：会话 hooks/memory 注入
（跨会话经验可能含本 issue 元信息）——S2 以 SDK `SessionManager.inMemory()`
+ 禁 ambient 收口；triage 节点同理可无工具化。

---

## 8. 度量与晋级判据

级别由度量定义，不由感觉定义（Shapiro：每一级都"感觉完成了"）。

| 阶段 | 出口判据（全部满足才晋级） |
|---|---|
| S0 治理 | ✅ 治理锁 + mutations 冒烟 kill rate 100%（篡改类） |
| S1 → L3 | fix-issue 全链路人工触发可用；3+ issue 并行；PIV 循环零人工；行为破坏类缺陷集扩充后 kill rate ≥80% |
| S2 → L4 | dispatcher 上线；连续 7 天无人干预 auto-merge ≥5 PR；holdout 误报率 <10%；cost/PR < 锁定上限 |
| S3 → L4.5 | 周度自愈回归回灌 ≥1 个真实回归；模型路由经 benchmark 矩阵校准；skill-evo 元闭环跑通 |
| **Shapiro 测试** | 离开 12 小时，回来 tests 全绿、PR 已合并、无 needs-human 堆积 |

反指标（同步监控，恶化即降级）：holdout 误报率、needs-human 率、每 PR 成本、
mutation kill rate 回归。

---

## 9. 风险登记册

| # | 风险 | 缓解 |
|---|---|---|
| R1 | label 抢占竞态（双 tick 同 issue） | 幂等 `--add-label` 抢占，失败放弃本 tick（§7） |
| R2 | prompt injection 经 issue/PR 正文直达 main | A6：正文只进 triage，结构化 JSON 下游；holdout 输入白名单 |
| R3 | 自举悖论：修 guard = 改裁判 | guard.py 与 .factory/ 全量在周界内，只能人类 PR 修改 |
| R4 | 成本失控 | locks/floor.json（S2）：每 PR 上限 + 每日总额，超限熔断停摆并 needs-human |
| R5 | SDK 依赖（Bun 版本、isTerminal 语义） | S1–S2 用 CLI 形态规避；SDK 直连仅白名单节点，接口已把坑写进注释（§4） |
| R6 | L3 心理陷阱（人生是 diff，感觉变糟就回退） | 级别 = §8 度量，不 = 感觉；反指标触发才降级 |
| R7 | triage 判据漂移（MISSION 语义模糊） | 判据三条保持可机械核对；歧义 case 记 decisions.md，季度人审收编 |
| R8 | 门腐化（新缺陷类型不在 mutation 集内） | 每次漏拦事故 → 新 defect 条目（坏例回归，badcase_runner 同思想） |

---

## 10. 与本仓库现状的映射（为什么不重复建设）

| 工厂组件 | 仓库既有资产 | 复用方式 |
|---|---|---|
| 确定性测试门 | `scripts/run_tests.sh`（7 套件 + badcase 双通道 + plugin_lock + md_link_check） | 直接引用，不包装 |
| 坏例回归 | `scripts/badcase_runner.py` | S1 扩编为 mutation 行为破坏类缺陷素材库 |
| 锁定先例 | `scripts/plugin_lock.py`（安装入口 zero-regression） | 治理锁思想同源，三层锁之一 |
| 元技能闭环 | `skills/skill-evo/`（会话经验提炼 → 人工审核 → GEPA 自进化） | 对应 drift/ablate/scan/evolution-review 四件套；decisions.md 喂入 |
| triage 依据 | `steering/*.md`（唯一真相源，人工维护） | fix-issue 的 prime 上下文 + 评审节点的规范依据 |
| AI 评审节点 | `skills/api-guard` `ddl-guard` `arch-guard` | validate-PR 按 PR 触及面选配的并行评审器 |
| hooks 注入 | `hooks/omp/load-steering.sh` | AI 节点会话自动携带治理上下文 |

---

## 11. 参考资料

- Dan Shapiro, *Five Levels: from Spicy Autocomplete to Dark Factory*（2026-01）
- github.com/coleam00/dark-factory-experiment（四铁律、GitHub 状态机、holdout）
- github.com/coleam00/skills（PIV 循环、元技能、build-dark-factory 模板）
- github.com/coleam00/Archon（YAML DAG 工作流引擎；本设计的对照组）
- 本地：`MISSION.md`、`.factory/guard.py`、`.factory/mutations/`
