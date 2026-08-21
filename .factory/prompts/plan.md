# 节点：plan（任务级实现计划）

基于 prime 研究笔记，产出可机械执行的计划。计划的质量标准：
implement 节点可以不做任何设计决策地照做。

## 输入（只读）

- `$ISSUE_DIR/issue.json`（含 `comments` 字段：重投/整改时人类的补充
  验收标准在评论里，**以评论为准**，正文不可覆盖评论要求）
- `$ISSUE_DIR/prime.md`

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
 "forbidden": ["MISSION.md", "CLAUDE.md", ".github/", "data/", "config/",
                "supabase/", "scripts/", "..."],
 "final_gate": "scripts/run_tests.sh --no-lock"}
```

stdout 最后一行输出：`ARTIFACT: $ISSUE_DIR/plan.json`
