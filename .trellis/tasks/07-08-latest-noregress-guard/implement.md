# C2 执行计划 · latest no-regress 护栏

## 前置
- `task.py start 07-08-latest-noregress-guard`(review 后)。可与 C3 并行(互不碰同文件:C2 改 pipeline latest 写入,C3 改 self_breadth)。

## 有序清单

### 步骤 1 — 判定纯函数(TDD)
1. 测试 `backend/tests/test_no_regress.py`:
   - existing=None → (True,'first')。
   - new_cn < existing_cn → (False, 含 'regress')。
   - new_cn == existing_cn(us 同)→ (True)。
   - new 更新 → (True)。
   - new_us < existing_us(cn 相等)→ (False)。
   - existing 缺 cn_data_date → 该侧不拦。
2. 实现 `backend/src/output/no_regress.py::should_write_latest`。
3. 验证:`cd backend && uv run --all-extras pytest tests/test_no_regress.py -v 2>&1 | tail -20`

### 步骤 2 — 接入 pipeline
1. 抽 `write_latest(...)` 包四文件写入 + 前置 no-regress 判定 + 跳过日志。
2. 测试(扩 `test_pipeline_*` 或新增):构造 latest 已有 07-07 meta,跑产出 07-06 数据 → 断言四文件未变;产出 07-08 → 断言已更新。可用 tmp data_root + 直接调 `write_latest`。
3. 验证 pytest。

### 步骤 3 —(可选)前端截至日
1. `Header/index.tsx` 加 as-of 展示(读 `meta.cn_data_date`),条件:非今日且未触发 StaleBanner。
2. 轻量组件测试或快照。`cd frontend && npx vitest run 2>&1 | tail -10`
3. 若时间紧可拆为独立收尾 PR。

### 步骤 4 — 全量回归
- `cd backend && uv run --all-extras pytest 2>&1 | tail -15`

## 验证命令
```
cd backend && uv run --all-extras pytest tests/test_no_regress.py tests/test_pipeline_compute_outputs.py -v 2>&1 | tail -25
cd backend && uv run --all-extras pytest 2>&1 | tail -15
```

## 风险 / 回滚
- 保守拦截(任一市场回退即跳过)可能在"单市场回退但另一市场有新数据"时也跳过 → 接受(宁可保留上一致版本)。若后续需精细化再按市场拆分写入。
- pipeline 接入独立可 revert。

## review 门
- 步骤 1、2 各 `trellis-check`;完成后 parent 集成。
- **待用户确认**:prd 的"回退全跳过"细化(vs D4 原述"写 stale meta")。确认后再实现步骤 2。

## 交界
- `latest_write_skipped_regress` 日志前缀 = C1 消费契约。
