# C3 · 温度链新鲜度护栏

> parent: `07-08-data-fetch-resilience`（D3 陈旧不静默）

## Goal
让市场温度/自建宽度链在**上游 close_series 陈旧时不再静默出图**:消费前校验新鲜度,陈旧则显式标记 + 可告警,而非像今天那样冻结在 07-06 还照常出温度图。

## 确认事实(代码勘察)
- `self_breadth.run`(`market_breadth/self_breadth.py:133-144`)盲读 `stocks/close_series.json`,直接算 `market_temperature.json`,**无任何新鲜度校验**——close_series 停 07-06 就出 07-06 的图。
- `reconcile`(`market_breadth/reconcile.py`)对账 self vs dapanyuntu,`over_threshold` 仅 `log.warning` + 写 `market_breadth_qc.json`,**无告警**;且它比的是 rate 差,不直接校验 self 的 as-of 日期是否达期望交易日。
- 交易日历 `etl/calendar.is_cn_trading_day` 可判期望交易日。
- `market_temperature.json` 已含 `dates`(末元素即 as-of)、`generated_at`。

## Requirements
- R3.1 **消费前新鲜度校验**:`self_breadth.run` 读 close_series 后,校验 `dates[-1]` 是否达期望 CN 交易日(收盘后);陈旧则:①在输出 `market_temperature.json` 增 `stale`/`as_of`/`expected_date` 标记;②`log.warning/error` 结构化前缀(供 C1)。
- R3.2 **不阻断出图**:陈旧仍产出(前端可展示"截至X日"),但标记明确——避免"有图=数据新"的错觉。是否硬阻断由 D1 自愈兜底,本任务默认标记不阻断。
- R3.3 **reconcile 陈旧信号强化**:当 `self.date < dapanyuntu.date`(as-of 落后)时,除 rate 偏差外单列 `self_stale: true` 到 qc.json,使 C1 能区分"方法学微差"与"真陈旧"。
- R3.4 (可选)复用 C4 `stocks_continuity` 判定 close_series 末日缺口,统一新鲜度口径。

## Acceptance Criteria
- [ ] 单测:close_series 末日 < 期望交易日 → `market_temperature.json` 含 `stale=true` + `as_of`;末日达标 → `stale=false`。
- [ ] 单测:reconcile 在 self.date<dpyt.date 时输出 `self_stale=true`;日期一致时 false。
- [ ] 非交易日/盘中不误判 stale(复用 calendar 口径)。
- [ ] 回归 `uv run --all-extras pytest` 全绿。

## Out of scope
- 修 close_series 本身陈旧(属 C4 补缺)。
- 告警推送(属 C1;C3 只产出可被消费的标记/日志)。
- 前端温度页 UI(如需展示 stale 标记可作后续小项)。

## 依赖 / 交界
- 与 C1 共享"陈旧信号"语义(market_temperature.stale / qc.self_stale / 日志前缀)。
- 可选复用 C4 `stocks_continuity`;未合入前用 `calendar` 直接判末日。
