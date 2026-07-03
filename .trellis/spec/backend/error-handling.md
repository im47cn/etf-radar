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
