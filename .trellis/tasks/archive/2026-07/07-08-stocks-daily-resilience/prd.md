# C4 · stocks-daily 韧性 + 自动补缺

> parent: `07-08-data-fetch-resilience`（决策 D1 全自动自愈 / D2 哨兵架构 / D3 Server酱告警）

## Goal
消除 stocks-daily 因网络抖动导致的**永久数据空洞**与**静默失败**:让漏天可被检测并自动补齐,让失败响亮暴露,从根上杜绝今天(07-07 被 CANCELLED → close_series 缺 07-07 → 市场温度冻结)的故障复现。

## 确认事实(代码勘察)
- `stocks_daily_pipeline._fetch_today_spot()` 用**实时** `ak.stock_zh_a_spot()`,只能取"当前"一格,**无法回补历史某日**(`stocks_daily_pipeline.py:39-43`)。→ 补缺只能走 `stocks-history-backfill`(按股票取历史日线,`stocks_history_pipeline`)。
- spot 失败时 `run_daily_pipeline` **静默 `return`**、不 append、不抛错(`stocks_daily_pipeline.py:132-136`)→ workflow 绿灯但数据不前进。静默失败第二条路径。
- `_append_series` 为追加模式 + 同日幂等替换(`:68-105`);漏一天则 dates 跳变(07-06→07-08),再跑 daily 不会插回 07-07 → 永久空洞。
- workflow `timeout-minutes: 10`(`stocks-daily.yml:18`);仅 git push 重试,pipeline 步骤本身无重试;job 被 CANCELLED 时后续步骤不执行。
- backfill 有独立并发组 `stocks-history-backfill` + `reset --hard origin/main` 后覆盖 `data/stocks`(整体重算获胜策略),已有 no-regress 护栏(`ea80d5c`)。
- 交易日历 `etl/calendar.py:is_cn_trading_day`(chinese_calendar)。

## Requirements
- R4.1 **步骤级重试**:`_fetch_today_spot()` 加带退避的重试(参照 provider 3 次模式);终失败**抛异常**(不再静默 return),使 workflow 变红。
- R4.2 **放宽 timeout**:`timeout-minutes` 10 → 25,给重试与 5528 股计算留余量。
- R4.3 **连续性检测**:新增函数/CLI,比对 close_series 尾部日期 vs 期望 CN 交易日,返回窗口内缺失交易日列表。
- R4.4 **自动补缺**:daily 成功后跑连续性检测,发现缺口 → `gh workflow run stocks-history-backfill.yml`(fire-and-forget,靠 backfill 并发组防叠加);检测/补缺动作留标记供 C1 哨兵与告警消费。
- R4.5 **不引入回归**:补缺依赖 backfill 既有 no-regress;daily 先提交自身再 dispatch backfill,避免 reset 冲突。

## Acceptance Criteria
- [ ] 单测:spot 首次失败、二次成功 → 正常 append(重试生效)。
- [ ] 单测:spot 连续失败 → 抛 `SpotFetchError`(非静默 return)。
- [ ] 单测:连续性检测对 `[...,07-06,07-08]`(07-07 为交易日)返回缺失 `[07-07]`;对连续序列返回空。
- [ ] 单测:非交易日缺口(周末)不误报。
- [ ] workflow:daily 成功后缺口检测步骤存在,缺口时执行 backfill dispatch;无缺口不 dispatch。
- [ ] 回归:`uv run --all-extras pytest` 全绿。
- [ ] 手动验证:构造缺口 → 触发 daily → 观察自动 dispatch backfill → close_series 补齐无空洞。

## Out of scope
- stocks-daily 自身取历史(spot 接口能力所限,交由 backfill)。
- C1 哨兵对"daily 根本没触发"的外部巡检(属 C1)。
- 更换 spot 数据源。

## 依赖 / 交界
- **产出供 C1 消费**:连续性检测函数(哨兵巡检复用)、缺口/失败标记语义。
- 若先于 C1 落地:R4.4 的 dispatch 逻辑内联在 stocks-daily.yml,自成闭环;C1 落地后哨兵额外覆盖 cancellation/漏触发。
