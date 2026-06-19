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
