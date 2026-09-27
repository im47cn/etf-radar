# 节点：prime（代码库定向研究）

读 issue 上下文，产出实现前的**研究笔记**。此时尚无 plan——不要设计解决方案，
不要写代码。

## 输入（只读）

- `$ISSUE_DIR/triage.json`（结构化裁决，accept 才会到达本节点）
- `$ISSUE_DIR/chain-history`（历史轮次证据：若含 `holdout ... verdict=FAIL`，
  其 evidence 是上轮验证器的拒绝理由——**本轮必须针对性消除**：通常是
  改动缺少可机械引用的验收证据，如为文档类改动补同步性测试）
- `$ISSUE_DIR/chain-history` 的 `node-fail`/`chain-abort` 行（若存在 =
  上轮链死因：`node-fail ... node=<名> reason=omp-exit|no-artifact|
  stale-artifact` = 该节点被预算击杀/崩溃或产物判定 fail-closed；
  `chain-abort ... exit=<码>` = 编排层死亡。上轮死因相关区域是本轮研究的
  优先对象）
- `$ISSUE_DIR` 下的 `*-pre-r*.*` 归档（若存在 = 本轮开始前的过程产物：
  prime 笔记/plan.json/implement 日志/review 结论，r 编号最大者最近）。
  **跨轮增量纪律**：仍成立的结论直接复用、不必重查——以 chain-history
  最近一次 `chain-start` 行的时间戳为 `git log --since` 起点，只研究此后
  的变化面；全量重查仅限首层（无归档可用）时
- 仓库内自由阅读：任务参数「仓库参数」段所列阅读范围

## 任务

1. 定位与本 issue 相关的既有模块、技能、脚本与测试布局
2. 找出必须复用的既有模式与约定（对应审查依据目录的哪些标准条款）
3. 记录牵连风险：哪些文件可能被改动波及、有无锁定约束（plugin_lock 等）
4. 明确完成判定的验证手段（哪个测试/脚本能证明完成）

## 输出

研究笔记用 write 工具写入 `$ISSUE_DIR/prime.md`，包含：
发现清单（文件路径 + 作用）、复用约定（规范条款引用）、
牵连风险、建议的验证命令。

stdout 最后一行输出：`ARTIFACT: $ISSUE_DIR/prime.md`
