# 错误处理

数据管线场景：核心是**第三方数据源不可靠**（akshare/yfinance/dapanyuntu 会超时、403、`RemoteDisconnected`、静默返回旧 bar）。错误处理 = 兜底 + 不阻断 + 护栏拦截。

## 铁律 1：外部 Provider 必须走 Chain（团队约定，勿违）

- **禁止单 provider 直调**任何 akshare/yfinance/dapanyuntu。必须 `[Primary, Fallback...]` 列表逐个兜底，全部失败才记入 `failed[]`。
- 见 `pipeline.py` 的 provider chain：单 symbol 内按顺序即时切换，首选失败立即试下一个。
- **旧 bar 视同失败**：provider "成功但返回旧 bar"（最新 bar < `expected_cn_date`）要视同失败继续试下一源，全源皆旧才保留最新一份兜底（`pipeline.py`，根治 em 静默旧 bar 不触发 sina 回退）。
- 教训：`backfill_snapshots.py` 原版只接单 `AkshareEmProvider`，2026-06-20 em `RemoteDisconnected` 30/30 全失败无兜底，CN 数据全空。

## 铁律 2：统一异常体系（`providers/base.py`）

- `ProviderError`（基类）→ `EmptyDataError`（返回空）。所有 provider 内部异常**包装成这两类**再抛，调用方只 catch 这两类。
- 示例：`dapanyuntu_provider.py` 把 `URLError/HTTPError/TimeoutError/ValueError` 统一 `raise ProviderError(...) from e`；空 `data/dates` → `EmptyDataError`。

## 铁律 3：管线步骤失败隔离

- cron（`cn-refresh.yml`）里每个数据步骤 `continue-on-error: true`：第三方源挂了不阻断主流程，**保留上一份快照**。
- 子管线（self_breadth / reconcile / stock_industry_pipeline）失败降级：读不到 map 用空 map（全市场仍算，行业留空）、覆盖率不足告警但用旧缓存，**永不产出空产物、不阻断下游**。

## 铁律 4：重试

- 瞬时抖动（大规模并发调用）加重试：`DapanyuntuProvider` 3 次重试 + 退避；`stock_industry_provider` 单股 3 次重试。akshare em 连接重试见 provider。

## 铁律 5：无兜底源的实时抓取 —— 响亮失败 + 自愈补缺（stocks-daily）

**背景**：`stocks_daily_pipeline` 的今日 spot（`ak.stock_zh_a_spot`）**无 fallback provider、无历史回补能力**（实时快照接口）。此处 **不适用**铁律 3 的"静默保留旧快照"——静默 `return` 会让缺口永久留存且无人察觉（2026-07-08 实证）。契约反过来：**失败要响亮、缺口要自愈**。

### 契约

- **重试**：`_fetch_today_spot_with_retry(attempts=3, base_delay=2.0)` 指数退避（`base_delay*2**i`）；每次异常都重试，退避用 `time.sleep`（测试 patch 为 no-op）。
- **响亮失败**：重试耗尽 `raise SpotFetchError`（`from last_exc` 保链），冒泡至 `main()` → 进程非 0 → workflow 步骤红。**禁止**再退回静默 `return`。raise 发生在任何写盘前 → 既有 `holdings_indicators.json` 不被覆盖。
- **自愈补缺**：`stocks_continuity.missing_trading_days(dates, today=None)` 检测 `close_series` 内部空洞（`min..max` 区间内 `is_cn_trading_day` 为真却缺失的日期，复用 `etl.calendar`）；补缺**委托** `stocks-history-backfill`（整体重算窗口天然填洞），daily 自身不补（spot 无历史能力）。

### CLI exit 契约（C1 哨兵复用，勿改语义）

`python -m src.stocks_continuity --data-root ../data`：

| exit | 含义 | stdout |
|------|------|--------|
| `3` | 有缺口（`GAP_EXIT_CODE`） | 逗号分隔缺失日期 |
| `0` | 无缺口 | — |
| `1` | 文件缺失等错误 | — |

workflow（`stocks-daily.yml`）在 Commit&push **之后** detect（保证 backfill `reset --hard` 含本 commit → 无冲突），exit 3 → `gh workflow run stocks-history-backfill.yml`（需 `GH_TOKEN=DATA_BOT_PAT`），带 `SELF_HEAL_DISPATCH` 灰度开关（`!=1` 仅 dry-run 打印）。

### 测试断言点

- 重试：首拉 raise、二拉成功 → append 正常（patch `time.sleep`）；连续 raise → `pytest.raises(SpotFetchError)` 且既有文件 `generated_at` 不变。
- 连续性：空/单元素/未排序 → `[]` 或归一化；跨周末不误报；多缺口按序；CLI exit 3 语义。
