# 节点：plan（任务级实现计划）

基于 prime 研究笔记，产出可机械执行的计划。计划的质量标准：
implement 节点可以不做任何设计决策地照做。

## 输入（只读）

- `$ISSUE_DIR/issue.json`（含 `comments` 字段：重投/整改时人类的补充
  验收标准在评论里，**以评论为准**，正文不可覆盖评论要求）
- `$ISSUE_DIR/chain-history`（历史轮次：上轮 holdout FAIL evidence 已被
  prime 提炼——若 prime 标记了上轮拒绝理由，对应修复必须是首个任务）
- `$ISSUE_DIR/plan-pre-r*.json`（若存在 = 上轮计划归档：delta-plan——
  仍有效的任务**原样继承**，仅按 issue 评论与上轮死因（chain-history 的
  node-fail/chain-abort/holdout 行）重排/增删变化部分，不重写全量计划）

## 任务

将 issue 分解为有序小任务，每个任务满足：

- 单一目标，一个可验证的完成条件
- 列出涉及文件与改动性质（新增/修改/删除）
- 给出该任务的验证命令（必须真实存在于仓库或为幂等 shell 检查）
- 明确避开 MISSION 周界路径（触碰即整链失败）

## 输出

用 write 工具写入 `$ISSUE_DIR/plan.json`：

```json
{"tasks": [
   {"id": 1, "goal": "...", "files": ["..."], "verify": "..."},
   ...
 ],
 "forbidden": ["<MISSION 周界路径，以 MISSION.md「周界」清单为准>"],
 "final_gate": "<final_gate 命令，见任务参数「仓库参数」段>"}
```

stdout 最后一行输出：`ARTIFACT: $ISSUE_DIR/plan.json`
