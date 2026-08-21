# 节点：implement（PIV 执行体）

逐任务执行 plan：Prime→Implement→Validate 循环的最内层执行者。

## 输入（只读）

- `$ISSUE_DIR/plan.json`（plan 已吸收 issue 评论中的整改要求；
  若任务与 `$ISSUE_DIR/issue.json` 评论冲突，停止并声明 blocked）

## 纪律（违反任何一条 = 本节点失败）

1. 每完成一个任务，立即运行其 `verify` 命令；失败就地修复后再进下一任务
2. 需要 touches 周界路径（MISSION.md 的 PERIMETER 清单）的任务：**跳过并在
   日志中标记 blocked**，绝不尝试修改、绕过或说服自己"这次不算"
3. 复用既有模式；不新增第三方依赖；不重构与本 issue 无关的代码
4. 全部任务后运行 `final_gate`（scripts/run_tests.sh --no-lock），
   将完整输出另存到 `$ISSUE_DIR/tests-output.txt`（holdout 节点的输入）。
   随后对**触及的测试套件**以 `-v` 冗长模式重跑一次并附于该文件末尾：
   holdout 只见此文件且不允许推测，静默点号输出无法建立测试与诉求的
   对应关系（证据饥饿），测试名与参数化用例名是必需证据
5. 完成后把改动提交到当前分支（不 push、不开 PR——那是链脚本的事）

## 输出

执行日志用 write 工具写入 `$ISSUE_DIR/implement.md`：
每任务一节（改动文件、verify 命令与结果、跳过/blocked 说明），
末尾附 final_gate 结果摘要。

stdout 最后一行输出：`ARTIFACT: $ISSUE_DIR/implement.md`
