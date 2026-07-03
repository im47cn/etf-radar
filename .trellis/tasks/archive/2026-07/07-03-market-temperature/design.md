# 技术设计 — 市场温度页面

## 1. 边界与总体数据流

```
dapanyuntu API ──► DapanyuntuProvider ──► market_temperature_pipeline ──► data/latest/market_temperature.json
  (每日16:00)        (httpx + headers)       (聚合L1 / 全市场均值 / 过滤0)              │
                                                                                        ├─► archiver → data/snapshots/<date>/market_temperature.json
                                                                                        └─► snapshots_index 重建
                                                                                                 │
                       前端 /temperature 页 ◄── useMarketTemperature (SWR + zod) ◄── /data/latest/market_temperature.json
```

设计原则：**新增独立管线步骤，不侵入现有 ETF pipeline 的 compute_outputs**。dapanyuntu 数据与 ETF/theme 计算完全解耦，单独 fetch + 单独写文件，仅在编排层（cn-refresh 流程）串到一起。

## 2. 后端组件

### 2.1 DapanyuntuProvider（`src/providers/dapanyuntu_provider.py`）
- 职责：拉取原始宽度数据。**不做聚合**（单一职责）。
- 接口：`fetch_breadth() -> BreadthRaw`，返回 `{data: list[[int,int,float]], dates: list[str], industries: list[str]}`。
- 实现：`httpx.get(url, headers={Referer, User-Agent}, timeout=20)`。
- 异常：403/超时/非 200 → `ProviderError`；空 `data`/`dates` → `EmptyDataError`。复用 `providers/base.py` 现有异常体系。
- 端点：`https://sckd.dapanyuntu.com/api/api/industry_ma20_analysis_page?page=0`。

### 2.2 行业映射（`src/market_breadth/industry_mapping.py`）
- 86 二级行业 → 26 一级行业的静态 dict，移植自 skill 的 `references/industry-mapping.md`。
- 提供 `L2_TO_L1: dict[str, str]` 与 `L1_ORDER: list[str]`。
- 未在映射表中的二级行业：归入 `"其他"` 并记 warning（防数据源新增行业静默丢失）。

### 2.3 计算管线（`src/market_temperature_pipeline.py`）
- `compute_market_temperature(raw: BreadthRaw) -> MarketTemperature`：
  - 解包稀疏三元组 `[date_idx, industry_idx, value]` 为 `{(date, industry): value}`，**过滤 value<=0**。
  - `industries_l2`：每个二级行业 → `{name, series[31], latest}`（缺失日填 `null`，非 0）。
  - `industries_l1`：对每个 (一级, date) 收集其下二级有效值取 **等权均值**，保留 1 位小数。
  - `market`：每个 date 对 **所有二级有效值** 取等权均值 → `[{date, rate}]`（口径：行业等权，与 skill 底部统计一致）。
  - 排序：行业按 **最新日期值降序**。
- `run(data_root)`：fetch → compute → `atomic_write_json(data_root/'latest'/'market_temperature.json')`。复用 `output/writer.py::atomic_write_json`。

### 2.4 快照结构（`data/latest/market_temperature.json`）
```json
{
  "schema_version": "1.0",
  "generated_at": "2026-07-03T08:00:00+00:00",
  "source": "dapanyuntu",
  "metric": "ma20_above_ratio",
  "dates": ["2026-05-19", "...31 个交易日"],
  "market": [{"date": "2026-05-19", "rate": 42.3}],
  "industries_l1": [{"name": "电子", "series": [42.1, null, ...], "latest": 42.1}],
  "industries_l2": [{"name": "半导体", "series": [38.0, ...], "latest": 38.0}]
}
```
- `series` 与 `dates` 等长、下标对齐；无数据位为 `null`。
- `latest` = series 最后一个非 null 值。

### 2.5 归档与索引
- `output/archiver.py`：latest→snapshots 复制已是「整目录」逻辑，`market_temperature.json` 随 latest 目录自动带入，**无需改动**（确认后如为白名单则加入）。
- `output/snapshots_index.py`：若索引按固定文件名清单构建，需 **补 `market_temperature_path`**；若为目录扫描则无需改。实现时先读该文件确认。

### 2.6 编排接入
- `cn-refresh` 流程（`.github/workflows/cn-refresh.yml` 调用的入口）在 ETF pipeline 后追加一步：`python -m src.market_temperature_pipeline`。
- **失败隔离**：dapanyuntu 拉取失败不应阻断 ETF 主流程 → 该步骤 `continue-on-error` 或在入口内 try/except 记录并跳过（保留上一份快照）。

## 3. 前端组件

### 3.1 数据层
- `types/marketTemperature.ts`：zod schema 校验快照，导出 TS 类型。
- `hooks/useMarketTemperature.ts`：SWR 拉 `/data/latest/market_temperature.json`，`revalidateOnFocus:false`，参照 `useEventsSnapshot` 模式。

### 3.2 页面与组件（`components/temperature/`）
- `TemperaturePage.tsx`：页面容器，持有 `level: 'l1' | 'l2'` 状态，向下分发。
- `MarketThermometer.tsx`：全市场当日大数字 + 冷热配色 + 31 日 mini sparkline。
- `IndustryRanking.tsx`：当日条形排行，接收 `level` 决定数据源（l1/l2），内置一级/二级 Toggle（提升到 Page 亦可）。
- `BreadthHeatmap.tsx`：行业×日期颜色矩阵，色阶复用 skill 浅色系（淡紫→浅蓝→浅绿→浅黄→浅橙），随 `level` 切换行集合。
- 复用 `components/ui/` 现有基础组件与 Tailwind 配色约定。

### 3.3 路由与导航
- `App.tsx` 增 `<Route path="/temperature" element={<TemperaturePage />} />`。
- Header/导航加「市场温度」入口，与 rotation/radar 并列。

## 4. 关键取舍与理由

| 取舍 | 选择 | 理由 |
|------|------|------|
| 全市场口径 | 行业等权均值 | 数据源无成分股数；与 skill 底部统计口径一致；页面明示 |
| 管线耦合 | 独立步骤，不进 compute_outputs | dapanyuntu 与 ETF 计算无依赖，解耦利于测试与失败隔离 |
| 主题维度 | 本期不做 | 数据源无个股，无法精确；避免误导性近似 |
| 缺失值 | `null` 非 0 | 0 在源数据中=无数据，当 0% 会污染均值与配色 |
| 历史长度 | 源返回的 31 日 | 单次请求即全量，无需自建历史累积 |

## 5. 兼容性 / 回滚

- 纯新增：新 provider、新 pipeline 文件、新快照文件、新前端路由，**不改现有 ETF 输出与页面**。
- 回滚：移除 cn-refresh 中新增步骤 + 前端路由/导航条目即可，历史快照文件无害残留。
- 前端对 `market_temperature.json` 缺失（旧快照）需优雅降级：hook 返回 undefined → 页面显示「暂无数据」。

## 6. 测试策略

- 后端：provider 解析（mock httpx 响应）、0 值过滤、L1 聚合正确性、全市场均值、行业排序、缺失日 null 填充。
- 前端：schema 解析、温度计数字/配色、排行排序、热力图列对齐、l1/l2 切换联动。
