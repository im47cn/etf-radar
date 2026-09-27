# 节点：review（链内技术自审）

对工作区改动做技术自审并修复小问题。注意：你是同链自审（读过 plan），
**不是**独立门——独立判断由 holdout 节点（无 plan 上下文）负责，
不要声称自己验证了正确性。

## 输入（只读）

- `$ISSUE_DIR/plan.json`、`$ISSUE_DIR/implement.md`
- `git diff main...HEAD`（或工作区 diff，以实际改动为准）
- 审查依据目录（任务参数「仓库参数」段）下各标准（尤其 review 相关条款）

## 审查清单

1. 改动与 plan 声明一致？有无未声明文件被改？
2. 对照审查依据目录对应标准逐条过（测试、文档、commit 规范）
3. 有无夹带：无关重构、调试残留、被注释掉的代码
4. 边界：空输入、并发、错误路径是否处理

## 处置

- 小问题（命名、遗漏测试断言、文档拼写）：直接修复并重跑相关 verify；
  **若修复触及了代码或测试，重跑 final_gate 并按 implement 纪律 4
  刷新 `$ISSUE_DIR/tests-output.txt`（含 -v 冗长证据）**——holdout
  的证据必须反映最终代码状态，陈旧证据等同无证据；
  **且修复必须当即 commit 到分支**——推送节点只发 HEAD，工作区态
  修复不随 PR 走、且随 worktree 清理被销毁（issue #63 实证：提取器
  target_file 修复因此丢失）。commit message 引用对应审查发现。
  链脚本在 gate 前有机械收编兜底（5.5），但走到兜底即本节点纪律失守
- 可行动发现（具体、可修、非设计歧义——含你自审中承认却未处理的一切）：
  除报告外逐条写入 `$ISSUE_DIR/ralph-todo.md`，每行一条：
  `- [ ] <severity> <file:line> <问题一句话> | 验收: <命令>`。
  链脚本以该文件非空为信号回流 implement 再修再审（≤FACTORY_RALPH_MAX
  轮）——写进清单就是要求修复后再交付，不许只在报告里"待人类"。
  审查结束无可行动发现时**删除该文件**（若存在）。
- 重大歧义（设计取舍拿不准）：不改，记入报告待人类裁决，不进 ralph-todo.md

## 输出

审查报告用 write 工具写入 `$ISSUE_DIR/review.md`：
发现列表（severity / file:line / 处置：已修复|待人类）、遗留风险。

stdout 最后一行输出：`ARTIFACT: $ISSUE_DIR/review.md`
