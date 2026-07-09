# C3 执行计划 · 温度链新鲜度护栏

## 前置
- `task.py start 07-08-temperature-freshness-guard`(review 后)。可与 C2 并行(改不同文件)。

## 有序清单

### 步骤 1 — self_breadth 新鲜度(TDD)
1. 测试 `backend/tests/test_self_breadth.py`(扩):
   - close_series dates 末日 < 期望交易日(注入固定 now_bjt,收盘后)→ 输出 `stale=true` + `as_of`/`expected_date`。
   - 末日 == 期望 → `stale=false`。
   - 盘中(未到结算)→ 不误报(expected 放宽上一交易日)。
2. 实现 `_freshness()` + `compute_self_breadth` 增字段 + `run()` 陈旧 log.warning。
   - now_bjt 需可注入(参数默认 `datetime.now`),便于测试固定时间。
3. 验证:`cd backend && uv run --all-extras pytest tests/test_self_breadth.py -v 2>&1 | tail -20`

### 步骤 2 — reconcile self_stale(TDD)
1. 测试 `backend/tests/`(reconcile 相关):self.date<dpyt.date → `self_stale=true`;相等 → false。补断言不破坏现有。
2. 实现 `reconcile()` 增 `self_stale` + 日志。
3. 验证 pytest。

### 步骤 3 — 前端兼容校验
- market_temperature.json 新增字段后,确认前端温度页/zod schema 不报错:
  `cd frontend && npx vitest run 2>&1 | tail -10`
- 若 zod strict 报未知字段 → 在对应 schema 加可选字段(as_of/stale)。

### 步骤 4 — 全量回归
- `cd backend && uv run --all-extras pytest 2>&1 | tail -15`

## 验证命令
```
cd backend && uv run --all-extras pytest tests/test_self_breadth.py -k "stale or fresh" -v 2>&1 | tail -20
cd backend && uv run --all-extras pytest 2>&1 | tail -15
```

## 风险 / 回滚
- 新增 JSON 字段可能触发前端 zod strict → 步骤 3 校验并同步类型。
- 两处改动独立可分别 revert;附加字段回滚不破坏既有消费。

## review 门
- 步骤 1、2 各 `trellis-check`;步骤 3 前端校验;完成后 parent 集成。

## 交界契约
- market_temperature.{stale,as_of,expected_date} 与 qc.self_stale + 日志前缀 = C1 消费。变更需同步 C1。
- 复用 C4 `stocks_continuity`(可选);未合入前用 calendar 直判。
