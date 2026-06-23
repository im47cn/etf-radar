# 主题下钻成分股 Phase 1 设计稿

- **日期**：2026-06-23
- **作者**：im47cn / Claude
- **状态**：设计已通过头脑风暴评审，待写入实施计划
- **关联**：[2026-06-21 portfolio-monitor-design](./2026-06-21-portfolio-monitor-design.md)

---

## 1. 背景与目标

### 1.1 背景
- 当前主题展示组件 (`ThemeRow`, `FocusedThemePanel`) 仅显示 ETF 代码列表，未展示 ETF 内的成分股
- 数据现状：28 个主题全部都有 `primary_cn`；11 个 A 股专属主题在美股视图下 `us_etfs` 为空，被用户感知为"主题下没有标的"
- 用户希望由主题向下钻取到"代表个股"，形成 主题 → ETF → 成分股 的完整研判链路

### 1.2 目标（Phase 1）
1. 为每个 A 股主题提供独立的成分股子页面，列出该主题对应 ETF 的合并 Top10 持仓
2. 显示个股的累计权重、关联 ETF、收盘价、今日涨跌
3. 美股主题在该页面显示"Phase 2 上线"占位
4. 不引入个股技术指标 / 基本面（推迟到 Phase 2 / Phase 3）

### 1.3 非目标
- 个股 RSI / MACD / 量比 / 换手率（→ Phase 2）
- 个股市值 / ROE / 龙头判定（→ Phase 3）
- 美股 ETF 持仓抓取（→ Phase 2/3）
- 主题级人工补充个股字段（→ Phase 3，与龙头判定统一设计）
- 个股 → 关联主题反向链路（独立 issue）

---

## 2. 架构总览

```
后端
├── 季度管道 holdings_pipeline (月初 cron)
│   └── akshare fund_portfolio_hold_em → data/holdings/{etf_code}.json
├── 日频增量 stocks_spot_pipeline (独立 cron，工作日交易时段每 30 min)
│   └── 一次 akshare stock_zh_a_spot_em → 筛选 holdings 涉及个股 → data/latest/stocks_spot.json
└── 新模型 Holding / ETFHoldings / StockSpot

前端
├── 新路由 /theme/:id/stocks
├── 入口: FocusedThemePanel 增加 "查看主题成分股" 按钮
├── 新页面 StocksPage + 组件 StockTable / EmptyState
└── 新 hooks useEtfHoldings + useStocksSpot + aggregator
```

### 关键决策

| 决策 | 原因 |
|---|---|
| 持仓走独立 `data/holdings/*.json`，不嵌入日频 snapshot | 季度数据进每日快照会无谓膨胀 diff |
| 个股 spot 写 `data/latest/stocks_spot.json`，只覆盖 holdings 涉及个股（约 200-500 只）| 避免拉全市场 5000+ 个股；用 latest 单文件避免每日 snapshot 膨胀 |
| 持仓抓取走独立 GitHub Action（月度 cron），不并入现有 cn-refresh | 避免每日 nightly job 调一次 28 个 ETF 持仓接口 |
| 个股 spot 走**独立** GitHub Action（30 min cron），不并入主 pipeline | 解耦 spot 失败与主链路 timestamp；提升刷新频率至盘中 30 min 级；写 `data/latest/` 会被 `deploy-frontend.yml` paths 自动触发部署（约 +14 次/天 deploy，GitHub Pages 免费额度可承受）|
| 前端聚合在 client-side | 不引入中间快照表，简化数据契约 |
| 入口集中在 `FocusedThemePanel` | 用户已在主题上下文中，认知负担最小 |

---

## 3. 数据契约

### 3.1 `data/holdings/{etf_code}.json`（季度更新）

```json
{
  "etf_code": "512480",
  "etf_name": "半导体ETF",
  "disclosure_date": "2026-03-31",
  "fetched_at": "2026-06-23T03:00:00+00:00",
  "top_holdings": [
    { "code": "002129", "name": "TCL中环", "weight": 8.5 },
    { "code": "603501", "name": "韦尔股份", "weight": 7.2 }
  ]
}
```

**字段说明**：
- `etf_code`：6 位 A 股 ETF 代码
- `disclosure_date`：季报披露截止日（YYYY-MM-DD）
- `fetched_at`：抓取时间（ISO 8601 带时区）
- `top_holdings`：按权重降序，长度 ≤ 10
- `weight`：百分比小数（0-100），保留 2 位

### 3.2 `data/holdings/index.json`（索引文件）

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-23T03:00:00+00:00",
  "etfs": [
    { "code": "512480", "disclosure_date": "2026-03-31" },
    { "code": "159870", "disclosure_date": "2026-03-31" }
  ]
}
```

### 3.3 `data/latest/stocks_spot.json`（盘中刷新单文件）

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-23T07:30:00+00:00",
  "stocks": {
    "002129": { "name": "TCL中环", "close": 12.5, "r_1d": 0.025 },
    "603501": { "name": "韦尔股份", "close": 98.7, "r_1d": -0.012 }
  }
}
```

**字段说明**：
- `stocks` 为对象（按代码查询），仅含 holdings 中出现的个股代码并集
- `r_1d` 为今日涨跌幅小数（如 0.025 = +2.5%），停牌或缺失时为 `null`
- 体积预估：单文件 30-80 KB，原地覆盖（不进 `data/snapshots/`）
- 刷新频率：工作日 BJT 09:00-15:30 每 30 min（由独立 cron 触发）

---

## 4. 后端设计

### 4.1 数据模型扩展（`backend/src/models.py`）

```python
class Holding(BaseModel):
    code: str        # A 股代码（6 位）或港股代码（5 位）
    name: str
    weight: float    # 占 ETF 净值百分比，0-100

class ETFHoldings(BaseModel):
    etf_code: str
    etf_name: str
    disclosure_date: date
    fetched_at: datetime
    top_holdings: list[Holding]  # len ≤ 10

class StockSpot(BaseModel):
    name: str
    close: float
    r_1d: float | None
```

### 4.2 季度持仓管道 `holdings_pipeline.py`（新增）

**位置**：`backend/src/holdings_pipeline.py`

**职责**：
1. 读取 `themes.yaml`，提取所有 `primary_cn` ETF 代码（去重）
2. 对每个 ETF 依次尝试最近 4 个季末日期（参见"季度推断规则"），取首个返回非空数据的季度
3. 单个 ETF 失败不影响其他（记录 warning）
4. 落盘 `data/holdings/{code}.json` 与 `index.json`

**季度推断规则**：
- 候选季度按降序：最近 4 个季末日期 `[最近季末, T-1, T-2, T-3]`
- 季末定义：`3/31`、`6/30`、`9/30`、`12/31`
- 对每个 ETF 独立判定，避免"季报披露错峰"导致整批失败
- 实际落盘的 `disclosure_date` 即首个成功的季末日期

**接口签名**：
```python
def run_holdings_pipeline(
    themes_yaml: Path,
    output_dir: Path,
    today: date | None = None,  # 测试可注入；生产用 date.today()
) -> HoldingsPipelineReport: ...
```

### 4.3 个股快照 `stock_spot_provider.py`（新增）

**位置**：`backend/src/providers/stock_spot_provider.py`

**职责**：
1. 扫描 `data/holdings/*.json` 收集个股代码并集
2. 调 `ak.stock_zh_a_spot_em()` 一次性拿 A 股全市场快照
3. 按持仓代码筛选并组装 `stocks_spot.json`
4. 原地写 `data/latest/stocks_spot.json`（不进 `data/snapshots/{date}/`）

**失败兜底**：
- 全市场 spot 调用失败 → 写空 `stocks_spot.json` + warning
- 单股缺失（停牌/退市）→ entry 缺失，前端按 `—` 展示

### 4.4 独立 pipeline 入口 `stocks_spot_pipeline.py`（新增）

**位置**：`backend/src/stocks_spot_pipeline.py`

stocks_spot 与主 pipeline **完全解耦**：

```python
# python -m src.stocks_spot_pipeline --data-root=./data
def main() -> None:
    args = parser.parse_args()
    write_stocks_spot_snapshot(
        out_path=args.data_root / 'latest' / 'stocks_spot.json',
        holdings_dir=args.data_root / 'holdings',
    )
```

**关键约束**：
- 主 `pipeline.py` **不再**调用 `write_stocks_spot_snapshot`（由反向回归测试 `test_main_pipeline_does_not_write_stocks_spot` 守护）
- spot 失败不会影响 `themes.json` / `etfs.json` / `signals.json` / `meta.json` 的时间戳
- 调用频率与主 pipeline 完全独立（30 min vs 5 min）

### 4.5 新增 GitHub Action `stocks-spot-refresh.yml`

**位置**：`.github/workflows/stocks-spot-refresh.yml`

**触发**：`cron: '*/30 1-7 * * 1-5'` = UTC 01:00-07:30 工作日 = BJT 09:00-15:30，每 30 min（每个交易日 14 次），支持 workflow_dispatch

**步骤**：
1. checkout（使用 `DATA_BOT_PAT` 以支持 commit-then-push）
2. setup-python + setup-uv（沿用 `cn-refresh.yml` 的 uv 重试策略）
3. 运行 `cd backend && uv run python -m src.stocks_spot_pipeline --data-root=../data`
4. 若 `data/latest/stocks_spot.json` 有变更，commit + pull-rebase + push

**部署链路**：本 workflow 仅 commit + push，**不**主动 trigger `deploy-frontend.yml`。但由于 `deploy-frontend.yml` 的 `paths` 监听 `data/latest/**`，push 后 deploy 仍会被自动触发。即前端会在每次 spot 更新后 ~3 min 拿到新数据。GitHub Pages 月度 build 额度（2000 min）远高于实际消耗（每次 ~3 min × 14 次/天 × ~21 工作日 ≈ 900 min/月），可承受。

**已考虑的替代方案**：在 `deploy-frontend.yml` paths 加 `!data/latest/stocks_spot.json` 实现"搭便车 cn-refresh deploy"。否决理由：前端价格延迟从 ~3 min 增加到最长 15 min，UX 损失 > 部署成本节省。

### 4.6 新增 GitHub Action `holdings-refresh.yml`

**位置**：`.github/workflows/holdings-refresh.yml`

**触发**：每月 1 日 00:30 UTC（cron `30 0 1 * *`），支持 workflow_dispatch

**步骤**：
1. checkout
2. 安装依赖（uv + akshare），沿用 `cn-refresh.yml` 一致的 setup
3. 运行 `cd backend && uv run python -m src.holdings_pipeline --data-root=../data --config-dir=../config`
4. 若 `data/holdings/` 有变更，commit 到 main 分支（沿用现有 commit-bot 模式）

### 4.7 后端文件清单

| 文件 | 操作 |
|---|---|
| `backend/src/holdings_pipeline.py` | 新增（含 CLI 入口 `if __name__ == "__main__"`）|
| `backend/src/providers/stock_spot_provider.py` | 新增 |
| `backend/src/stocks_spot_pipeline.py` | 新增（独立 CLI 入口；不被 `pipeline.py` 调用）|
| `backend/src/models.py` | 增加 Holding / ETFHoldings / StockSpot |
| `backend/src/pipeline.py` | **不**写 stocks_spot（由独立 pipeline 负责，保留反向回归测试守护）|
| `.github/workflows/holdings-refresh.yml` | 新增（月度，月初触发）|
| `.github/workflows/stocks-spot-refresh.yml` | 新增（盘中 30 min 一次；自动经 `data/latest/**` paths 触发 deploy）|
| `backend/tests/test_holdings_pipeline.py` | 新增 |
| `backend/tests/test_stock_spot_provider.py` | 新增 |
| `backend/tests/test_stocks_spot_pipeline.py` | 新增（含 `test_main_pipeline_does_not_write_stocks_spot` 反向回归）|
| `backend/tests/contracts/test_holdings_schema.py` | 新增 |

---

## 5. 前端设计

### 5.1 路由

```tsx
// frontend/src/App.tsx
<Route path="/theme/:id/stocks" element={<StocksPage />} />
```

### 5.2 类型定义（`frontend/src/types/holdings.ts` 新增）

```ts
export interface Holding {
  code: string;
  name: string;
  weight: number;
}

export interface ETFHoldings {
  etfCode: string;
  etfName: string;
  disclosureDate: string;  // YYYY-MM-DD
  fetchedAt: string;
  topHoldings: Holding[];
}

export interface StockSpot {
  name: string;
  close: number;
  r1d: number | null;
}

export interface AggregatedStock {
  code: string;
  name: string;
  cumulativeWeight: number;
  sourceEtfs: string[];   // 出现在哪些 ETF 中
  spot: StockSpot | null;
}
```

### 5.3 Hook：`useEtfHoldings`（新增）

**位置**：`frontend/src/lib/holdings/useEtfHoldings.ts`

```ts
useEtfHoldings(etfCodes: string[]): {
  data: ETFHoldings[];
  loading: boolean;
  error: Error | null;
}
```
- 并发 fetch `/data/holdings/{code}.json`
- 单个 404 / 网络失败不影响其他 ETF
- 返回顺序与入参对齐

### 5.4 Hook：`useStocksSpot`（新增）

**位置**：`frontend/src/lib/holdings/useStocksSpot.ts`

```ts
useStocksSpot(): Record<string, StockSpot> | null
```
- 从 `data/latest/stocks_spot.json` 加载（独立单文件，不依赖 snapshot 索引）
- 404 时优雅退化为 `null`，UI 价格列按 `—` 展示

### 5.5 聚合函数：`aggregator.ts`（新增）

**位置**：`frontend/src/lib/holdings/aggregator.ts`

```ts
aggregateHoldings(
  holdingsList: ETFHoldings[],
  spots: Record<string, StockSpot>,
): AggregatedStock[]
```
**规则**：
- 同一股票出现在多个 ETF 中，权重累加，`sourceEtfs` 收集所有 ETF 代码
- 按 `cumulativeWeight` 降序排序
- spot 缺失时 `spot = null`

### 5.6 组件结构

```
StocksPage (/theme/:id/stocks)
├── 顶部
│   ├── <BackButton/>
│   ├── 主题名 + "A 股专属" / "美股暂不支持" 标签
│   └── 关联 ETF 概览：列出该主题包含的 ETF 代码 + 披露日期
└── 主体
    ├── StockTable（数据齐全时）
    │   ├── 列: 序号 | 代码 | 名称 | 关联 ETF (chips) | 累计权重% | 收盘 | 今日涨跌
    │   ├── 默认按累计权重降序
    │   └── 行点击：复制代码到剪贴板，toast 提示
    └── EmptyState（无持仓数据时）
        └── "本主题暂无持仓披露，将在下个季度更新"
```

### 5.7 入口

**主入口**：`FocusedThemePanel` 底部新增按钮
```tsx
<Button onClick={() => navigate(`/theme/${theme.id}/stocks`)}>
  查看主题成分股 →
</Button>
```

**辅入口**：暂不在 `ThemeRow` 加图标（避免列表行视觉混乱）

### 5.8 颜色与样式
- 涨跌色与现有 `ThemeRow` 完全一致：涨用 `text-blue-600`、跌用 `text-red-600`（项目历史选型，本期不变更）
- 表格样式复用 `ThemeList` 既有 Tailwind 类，避免引入新 UI 风格

### 5.9 前端文件清单

| 文件 | 操作 |
|---|---|
| `frontend/src/pages/StocksPage.tsx` | 新增 |
| `frontend/src/components/stocks/StockTable.tsx` | 新增 |
| `frontend/src/components/stocks/EmptyState.tsx` | 新增 |
| `frontend/src/lib/holdings/useEtfHoldings.ts` | 新增 |
| `frontend/src/lib/holdings/useStocksSpot.ts` | 新增 |
| `frontend/src/lib/holdings/aggregator.ts` | 新增 |
| `frontend/src/types/holdings.ts` | 新增 |
| `frontend/src/components/rotation/FocusedThemePanel.tsx` | 添加按钮 |
| `frontend/src/App.tsx` | 添加路由 |
| `frontend/src/lib/holdings/__tests__/aggregator.test.ts` | 新增 |
| `frontend/src/lib/holdings/__tests__/useEtfHoldings.test.ts` | 新增 |
| `frontend/src/components/stocks/__tests__/StockTable.test.tsx` | 新增 |
| `frontend/src/pages/__tests__/StocksPage.test.tsx` | 新增 |
| `e2e/stocks-page.spec.ts` | 新增 |

---

## 6. 错误处理与空态

| 场景 | 行为 |
|---|---|
| 单个 ETF 持仓抓取失败 | 保留旧 JSON（最长容忍 1 季度未更新），UI 标注披露日期 |
| 个股 spot 全市场调用失败 | 写空 `stocks_spot.json`，前端按 `—` 展示 |
| 单股 spot 缺失（停牌/退市）| entry 缺失，UI 该列显示 `—` |
| 主题无任何 ETF 持仓数据 | 显示 EmptyState "本主题暂无持仓披露" |
| 美股专属主题（无 primary_cn）| 显示 "本主题美股个股数据 Phase 2 上线" 占位 |
| 港股通持股（如 00700）| `Holding.code` 保留原始代码，spot 跳过非 A 股代码，UI 显示 "港股暂不支持显示行情" |
| 路由参数指向不存在的主题 | 显示 404 占位，提供"返回主题列表"按钮 |

---

## 7. 测试策略

### 7.1 后端测试

| 测试文件 | 关键用例 |
|---|---|
| `tests/test_holdings_pipeline.py` | ① mock akshare 返回 → 验证 JSON 落盘格式<br>② 单个 ETF 抓取失败 → 其他 ETF 继续<br>③ index.json 完整列出所有成功的 ETF<br>④ 跨季度调用（季报披露前后）→ 取最新可用季度 |
| `tests/test_stock_spot_provider.py` | ① mock spot 全市场快照 → 验证按 holdings 代码过滤<br>② 全市场 spot 调用失败 → 写空文件 + warning<br>③ 持仓中存在的代码在 spot 中不存在 → 优雅跳过 |
| `tests/test_models.py`（扩展）| Holding / ETFHoldings Pydantic 校验：权重范围、code 格式 |
| `tests/contracts/test_holdings_schema.py` | 用 jsonschema 校验 `data/holdings/*.json` 与 `stocks_spot.json` 的契约 |

### 7.2 前端测试

| 测试文件 | 关键用例 |
|---|---|
| `lib/holdings/__tests__/aggregator.test.ts` | ① 单 ETF 持仓直接展开<br>② 多 ETF 同一股票权重累加<br>③ spot 缺失时 close/r_1d 为 null |
| `lib/holdings/__tests__/useEtfHoldings.test.ts` | ① 并发 fetch 多 ETF<br>② 单个 ETF 404 不影响其他<br>③ loading / error 状态正确 |
| `components/stocks/__tests__/StockTable.test.tsx` | ① 按累计权重排序<br>② 涨跌色正确<br>③ 空态渲染 |
| `pages/__tests__/StocksPage.test.tsx` | ① 路由参数读取<br>② 主题不存在显示 404 占位<br>③ 美股主题显示"暂不支持"提示 |
| `e2e/stocks-page.spec.ts`（Playwright）| 从 FocusedThemePanel 按钮 → 子页面 → 表格渲染 → 返回 |

### 7.3 数据契约自测
新增 `backend/tests/contracts/test_holdings_consistency.py`：
- 验证 holdings 中出现的所有个股代码，在最新 snapshot 的 `stocks_spot.json` 中都有 entry（除停牌情况）
- 验证 `index.json` 中列出的所有 ETF 都有对应文件

---

## 8. 风险与缓解

| 风险 | 缓解方案 |
|---|---|
| **akshare `fund_portfolio_hold_em` 接口不稳定 / 字段变更** | Phase 1 第一步先做 spike：用真实代码（512480、159870 等）跑 3-5 次确认返回结构。封装 provider 时严格做字段映射 |
| **季度数据滞后**（3 月只能拿到去年 Q4 持仓） | UI 醒目展示 `disclosure_date`，必要时显示"距披露日 X 天" |
| **港股通 / 跨市场代码混入**（如腾讯 00700） | `Holding.code` 字段允许非 6 位代码；spot provider 跳过非 A 股代码并 warning，UI 显示"港股暂不支持显示行情" |
| **个股 spot 调用拖慢主 pipeline** | 已通过独立 cron 解耦：spot 失败不影响主链路 timestamp，由 `test_main_pipeline_does_not_write_stocks_spot` 反向回归守护 |
| **盘中 30 min cron 偶发 push 冲突**（与 cn-refresh commit-bot 同分支） | workflow 使用 `git pull --rebase` 后 push；`concurrency: stocks-spot-refresh` 避免自身重叠 |
| **持仓数据缺失主题** | EmptyState 明确告知，不阻塞其他主题正常使用 |
| **GitHub Pages 静态资源缓存** | `data/holdings/*.json` 通过现有 CDN，刷新策略与 themes.json 一致（commit hash 影响 ETag） |
| **季度首日 cron 抢跑披露窗口** | 每月 1 日运行，但披露窗口是 1-2 月（年报）、4-5 月（一季报）等。如果抓不到最新季度，退到最近可用季度，记录 stale 标记 |
| **客户端聚合开销**（200-500 只个股的合并 + 排序）| 体量很小，单次渲染 < 5ms，不需要 web worker |

---

## 9. 上线 Checklist

- [ ] akshare `fund_portfolio_hold_em` spike 验证通过（接口可用 + 字段稳定）
- [ ] holdings 数据全量首次落盘，所有 A 股主题至少有 1 个 ETF 有 Top10 数据
- [ ] `data/latest/stocks_spot.json` 由独立 cron 产出可用
- [ ] 前端子页面在 dev 环境正常渲染（含 EmptyState）
- [ ] 单元测试 + 契约测试全绿
- [ ] Playwright e2e 通过
- [ ] 部署到 GitHub Pages 生产后烟雾测试新数据 URL（`data/holdings/index.json`、`data/latest/stocks_spot.json`）
- [ ] `docs/CONVENTIONS.md` 或 README 补充新数据契约文档

---

## 10. 后续 Phase 预告

| Phase | 范围 | 工期估算 |
|---|---|---|
| **Phase 2** | 个股技术指标：RSI / MACD / 量比 / 换手率 + 个股 daily K 线管道 + 强度评分 | 1-2 周 |
| **Phase 3** | 个股基本面：市值 / ROE + 龙头判定规则 + 主题级人工补充字段 | 1-2 周 |
| **Phase 4**（可选）| 持仓数据接入 portfolio event 系统（持仓股异动事件） | 1 周 |

Phase 2/3 的设计稿将在 Phase 1 上线后独立创建，避免过早设计带来的契约迭代成本。

---

## 修订记录

| 日期 | 提交 | 变更 |
|---|---|---|
| 2026-06-23 | (初版) | Phase 1 设计稿首次发布 |
| 2026-06-23 | `74712ee` | **拆分 stocks_spot 为独立 pipeline + cron**。原方案让 `pipeline.py` 在 cn 模式 snapshot 后顺带写 stocks_spot，与主链路耦合。重构后：新增 `backend/src/stocks_spot_pipeline.py` 独立 CLI；主 `pipeline.py` 不再写 stocks_spot（反向回归测试守护）；新增 `.github/workflows/stocks-spot-refresh.yml`（工作日交易时段 30 min cron）。收益：spot 失败与主链路解耦；刷新频率从日级提升到 30 min；前端 `useStocksSpot` 改读 `data/latest/stocks_spot.json` 单文件。|
| 2026-06-24 | (本次) | **修正"搭便车 deploy"叙述**。首次 workflow_dispatch 验证发现 `deploy-frontend.yml` paths 监听 `data/latest/**`，stocks-spot push 后会自动触发 deploy（非原假设的"不触发"）。审视后接受：前端价格延迟 ~3 min < 原方案 15 min，UX 更好；GitHub Pages 月额度足够。更新 §2 决策表 / §4.5 部署链路 / §4.7 文件清单的相关描述。|
