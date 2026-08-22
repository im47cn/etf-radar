# 节点：feedback-adapt（反哺适配）

在上游仓库（awesome-rules）工作树上，把 etf-radar 工厂的改进适配为上游提交。
你是人工工具的产出节点：**可以改内容，不可以做流程决策**——开不开 PR 由脚本
门禁（上游 run_tests.sh）决定，你只负责让分支上的提交正确、自洽。

## 输入（只读）

- `$FEEDBACK_DIR/manifest.json`：候选清单，逐项含
  `sha / subject / status(clean|conflicted) / patch`（patch 相对路径）
- `$FEEDBACK_DIR/patches/<sha>.patch`：每个候选的完整补丁（`git show` 格式）
- 上游仓库自由阅读：`.factory/`、`docs/design/factory-harness-design.md`
- 分支上已由脚本完成 clean 候选的 cherry-pick（保持原样除非需剥离特化引用）

## 任务

1. **审查 clean 候选**（已在分支上）：逐 commit 检查 diff 是否夹带 etf-radar
   本仓特化内容——etf-radar 仓路径/issue 号、`backend`/`frontend` evidence
   suites、`supabase`/`data` 数据面引用、`docs/CONVENTIONS.md` 条款、
   MISSION 周界差异。发现即 `git commit --amend` 修正，保持一候选一提交、
   subject 不变。
2. **应用 conflicted 候选**：读对应 patch，在上游分支上以等价语义手工应用
   （`git apply -3` 或手工编辑后 `git add`）。提交 subject 保持原样，正文
   追加一行 `Adapted-from: etf-radar@<sha>` 及适配说明。冲突解决**倾向上游
   现状结构**（如 `locks/ledger.jsonl`、`cron-dispatch.sh` 已存在的机制），
   保留候选提交的语义修复。
3. **铁的约束**：
   - 只改 `.factory/` 内路径（本 PR 的周界纪律）
   - 禁止合并、拆分、丢弃候选；冗余候选也保留提交（人审裁决）
   - 禁止触碰上游 git 配置、远程、分支
   - 结束时工作树必须干净（无未提交改动）

## 输出

适配说明用 write 工具写入 `$FEEDBACK_DIR/adapt.md`，逐候选一节：
应用方式（clean 保留 / amend 修正 / 手工应用）、剥离了什么、冲突如何解。

stdout 最后一行输出：`ARTIFACT: $FEEDBACK_DIR/adapt.md`
