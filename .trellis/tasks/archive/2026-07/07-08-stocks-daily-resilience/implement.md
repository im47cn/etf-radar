# C4 执行计划 · stocks-daily 韧性 + 自动补缺

## 前置
- 活动任务需切到本子任务:`python3 ./.trellis/scripts/task.py start 07-08-stocks-daily-resilience`(会挂起当前 membership-digest,需用户确认)。
- 分支:在 main 上新建工作分支(不直接改 main)。

## 有序清单

### 步骤 1 — 连续性检测模块(TDD 先行)
1. 写测试 `backend/tests/test_stocks_continuity.py`:
   - `[..., '2026-07-06', '2026-07-08']`(07-07 工作日)→ `[date(2026,7,7)]`。
   - 连续交易日序列 → `[]`。
   - 跨周末 `['2026-07-03(周五)', '2026-07-06(周一)']` → `[]`(周末非交易日不报)。
   - 空/单元素 → `[]`。
2. 实现 `backend/src/stocks_continuity.py`:`missing_trading_days()` 纯函数 + `main()` CLI(exit 3 有缺口 / 0 无 / 其他为错误)。
3. 验证:`cd backend && uv run --all-extras pytest tests/test_stocks_continuity.py -v 2>&1 | tail -20`

### 步骤 2 — spot 重试 + 响亮失败
1. 扩 `backend/tests/test_stocks_daily_pipeline.py`(或新建):
   - monkeypatch `_fetch_today_spot`:首次 raise、二次返回 DataFrame → append 成功。
   - 连续 raise → `run_daily_pipeline` 抛 `SpotFetchError`。
   - patch `time.sleep` 为 no-op 避免测试等待。
2. 实现 `SpotFetchError` + `_fetch_today_spot_with_retry`;改 `run_daily_pipeline` line 132-136 静默 return → 重试 + 终失败 raise。
3. 验证:`cd backend && uv run --all-extras pytest tests/test_stocks_daily_pipeline.py -v 2>&1 | tail -20`

### 步骤 3 — workflow 编排
1. 改 `.github/workflows/stocks-daily.yml`:
   - `timeout-minutes: 10 → 25`。
   - Commit & push 之后加 "Detect gaps & self-heal" 步骤(见 design.md),带 `GH_TOKEN: ${{ secrets.DATA_BOT_PAT }}`。
   - 首版可给 dispatch 加开关(如 env `SELF_HEAL_DISPATCH=1`)便于灰度;确认无误后默认开。
2. YAML 语法自检:`python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/stocks-daily.yml'))"`

### 步骤 4 — 全量回归
- `cd backend && uv run --all-extras pytest 2>&1 | tail -15`

### 步骤 5 — 手动端到端验证(可选,谨慎)
- 在测试分支人为构造 close_series 缺口 → 手动 `gh workflow run stocks-daily.yml` → 观察 detect 步骤输出 exit 3 → 确认 dispatch 了 backfill。
- 注意:真实 dispatch 会跑 backfill(~11-23min)。可先用 dry-run 开关只验证检测与分支逻辑。

## 验证命令汇总
```
cd backend && uv run --all-extras pytest tests/test_stocks_continuity.py tests/test_stocks_daily_pipeline.py -v 2>&1 | tail -25
cd backend && uv run --all-extras pytest 2>&1 | tail -15
```

## 风险文件 / 回滚点
- `stocks_daily_pipeline.py`:改了 spot 失败语义(绿→红),重点回归。独立 revert 可恢复旧行为。
- `stocks-daily.yml`:self-heal 步骤有 dry-run/开关兜底;dispatch 出问题不影响 daily 主流程(在 push 之后)。
- 新增 `stocks_continuity.py` 纯新增,零回归面。

## review 门
- 步骤 1、2 完成后各自 `trellis-check`(Agent)一次。
- 步骤 3 workflow 改动人工 review(CI 无法本地完整验证)。
- 全部完成后 parent 集成回归 + `trellis-update-spec`。

## 交界提醒(供 parent / C1)
- `stocks_continuity.missing_trading_days` 与 CLI exit 语义(3=有缺口)是 C1 哨兵复用契约,变更需同步 C1。
