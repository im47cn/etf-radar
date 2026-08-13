# 协作约定

本文档沉淀人 + AI 协作过程中形成的项目级约定。AI agent（Claude Code、Codex 等）和团队成员都应遵循。

## 文档与代码分离

- `docs/superpowers/plans/*` 和 `docs/superpowers/specs/*` 默认**不入 git 历史**，作为执行期间的临时载体。
- 若已存在误提交（如 `eb55d47`），不强制 revert；但后续 plan/spec 必须保留为工作区未跟踪文件，依赖人工 `git add` 显式提交而非任何 subagent。
- TODO（机制兜底）：考虑加入 `.gitignore` 或 pre-commit hook 阻断 `docs/superpowers/plans/*.md` 与 `docs/superpowers/specs/*.md` 进入 staging。

## Context 恢复纪律

- 每次 context 压缩、`/clear` 后或长时间空闲恢复，**第一动作必须**是 `git log --oneline -10` + `git status --short` 校准。
- 不得基于压缩前的"工作区状态"记忆做编辑/staging/commit 决策；任何 `M` 或 `??` 都必须重新验证。
- 触发条件：在对话摘要中读到"未 commit"、"工作区有改动"、"stage 后再 commit"等语句时，**强制走一遍校准**。

## Subagent-Driven 双审顺序

- 默认按 `superpowers:subagent-driven-development` 流程：spec 通过后再 code quality。
- **仅当 task 已 commit 不可逆**时，可并行调度两位审查员节省时间。
- 任务串行链路上（实施者 → 审查 → 下一个实施者），坚持顺序双审，避免审查员漏检"下游破坏由后续 task 修复"的过渡状态。
- 审查员若提出 Critical 反馈，先核对是否属于规格内置豁免（plan 中 Step N "暂不修复"等），再决定是否阻断。

## 外部 Provider 调用必须走 Chain

- 任何调用 akshare / yfinance / 类似第三方数据源的代码路径（pipeline、backfill、ad-hoc 脚本），**禁止单 provider 直调**。
- 必须沿用 pipeline 的 chain 模式：`[Primary, Fallback...]` 列表，逐 provider 兜底，全部失败才记入 `failed[]`。
- 触发条件：写或 review 任何 `*Provider().fetch_*` 调用时，确认上游是 list 而非单实例。
- 教训：`backfill_snapshots.py` 原版只接单 `AkshareEmProvider`，2026-06-20 遇 em 服务 `RemoteDisconnected` 30/30 失败时无兜底，CN 数据全空（commit `1974737` 修复）。

## Schema 演进必须同时 hotfix 旧数据兼容

- 任何对 snapshot/output schema 的字段新增（如 `us_strength` + `cn_strength` 双池），**前端 zod schema 必须用 `.nullish().transform(v => v ?? null)`** 同时接受 `null` 和 `undefined`。
- 历史 snapshot 字段缺省（`undefined`）不能因严格校验失败导致 trail / timeline 整批回退到 empty。
- 触发条件：PR diff 含 `schema_version` 变更，或 zod schema 新增非可选字段时。
- 教训：PR #14 schema 1.0→1.1 后，前端 `.nullable()` 拒绝缺省键，导致历史 frame 全部解析失败、trail 隐形不显示（commit `57bf242` 用 `.nullish()` 兜住）。

## 用户视角枚举 vs 数据属性枚举：概念分离

- UI MarketView 值（`'us' | 'cn-all'`，用户选的视角）与 Theme 属性 `isCnOnly()`（`primary_us === null`，数据特征）**是两套独立概念**，命名可能撞字符串。
- 删/改其一时，grep 全仓库后**必须按语义分类**：哪些是 MarketView 值（删），哪些是 Theme 属性（保留）。
- 触发条件：删除/重命名任何 UI 状态枚举值时。
- 教训:2026-06-20 删除 `cn-only` MarketView 选项时,fixture/trail 计算/MappingPanel 中的 `cn-only` 是 Theme 标签语义,误删会破 trail 渲染逻辑(commit `16ccff4` 已隔离两者)。

## 变更行覆盖率：避开 v8 coverage 盲区

- 变更行覆盖率 ≥90% 是 pre-commit/pre-push 红线（见 CLAUDE.md），由 `diff-cover` 对 staged 变更行判定。前端用 `@vitest/coverage-v8`，backend 用 `pytest-cov`。
- **盲区**：`arr.map(() => ({ ...多行对象... }))` / `arr.filter(() => ({ ... }))` 等**箭头函数返回多行对象字面量**的整个对象体，v8 coverage **完全不 instrument**——`coverage/lcov.info` 里这段 `DA` 记录整段缺失。diff-cover 会把对象体内的变更行判为 missing。
- 这不是"测试没覆盖"（组件确实渲染了），而是工具盲区。当某次 commit 只改这类对象体里的 1-2 行时，分母小、一行 missing 就砸到 ~80%，直接阻断 push。
- **规避写法**：需 diff-cover 保障的代码，把多字段对象构造改成 `for` 循环 + 独立 `const` + 单行 `push`，让每个计算都是 coverage 能捕获的独立语句：
  ```ts
  // ❌ 对象体整段无 DA 记录
  const data = arr.map((e) => ({
    a: e.a,
    b: e.b ?? 0,
    flag: e.flag ?? false,
  }));
  // ✅ 每行独立语句, coverage 必捕获
  const data: Row[] = [];
  for (const e of arr) {
    const flag = e.flag ?? false;
    data.push({ a: e.a, b: e.b ?? 0, flag });
  }
  ```
- 触发条件：前端 `.ts/.tsx` 变更涉及 `map`/`filter`/`reduce` 返回多行对象字面量，且 pre-push 报 diff-cover <90% 但肉眼明知测试已渲染。
- 教训：2026-08-13 `ArchTimeSeries.tsx` 的 `timeSeries.map((e) => ({...}))` 对象体内 label 行（line 23）lcov 整段无 DA，diff-cover 判 80% 阻断 push（commit `874f6bd` 改 for 循环后 100%）。
- 验证命令（本地复现 pre-push 流程）：
  ```bash
  cd frontend && ./node_modules/.bin/vitest run --coverage
  sed -i.bak 's|^SF:src/|SF:frontend/src/|' coverage/lcov.info && rm -f coverage/lcov.info.bak
  cd ../backend && uv run --all-extras diff-cover ../frontend/coverage/lcov.info --compare-branch=origin/main --fail-under=90
  ```
