# 技术设计 — 个股宽度多周期自建管线

## 1. 总体数据流

```
[已有] stocks_history_pipeline (新浪, days=150) ──► data/stocks/close_series.json (5531×150d close)
[新增] stock_industry_pipeline (东财/申万) ──────► data/stocks/stock_industry_map.json (个股→东财二级行业)
                                                          │
                              [新增] market_breadth/self_breadth.py
                              逐股 SMA20/60/120 → 站上判定 → 按行业+全市场聚合(每周期)
                                                          │
                                                          ├─► data/latest/market_temperature.json  (schema 2.0, 多周期, 自算)
                                                          │
[保留] dapanyuntu MA20 ──► 对账 ──► data/latest/market_breadth_qc.json (自算 vs dapanyuntu 偏差, QC)
                                                          │
                        前端 /temperature: 全局 MA20/60/120 切换, 三块联动
```

**解耦原则**：宽度计算是纯函数（close_series + 行业映射 → 快照），与抓取/映射/对账分离，单独可测。

## 2. 后端组件

### 2.1 历史深度加深（改现有）
- `stocks_history_pipeline.py:173` `--days` 默认 75→150；同步 `.github/workflows/stocks-history-backfill.yml` 默认值。
- `stocks_daily_pipeline.py:32` `WINDOW_DAYS` 75→150（否则每日截回 75，MA120 永远算不出）。
- 一次性手动 `workflow_dispatch` backfill days=150 铺底。
- 校验：close_series `dates` 长度 ≥150。

### 2.2 股票→行业映射（新增；**M0 已定源=巨潮**）
- 源：`ak.stock_industry_change_cninfo(symbol=<6位code>)`（巨潮，M0 唯一本机确认可用）。
  - 每股返回多分类标准多行（巨潮/中证/旧版，含变更历史）→ **筛选规则**：取 `分类标准=='巨潮行业分类标准'` 且 `变更日期` 最新的一行，用其 `行业大类`(→L1) 与 `行业中类`(→L2)。
  - taxonomy 从数据自然长出，**无需手维护映射表**（弃用/保留 `industry_mapping.py` 的东财表——该表仅供 dapanyuntu 侧继续用）。
- `src/providers/stock_industry_provider.py`：单股拉取 + 筛选 + 异常包装。
- `src/market_breadth/stock_industry_pipeline.py`：**复用 `stocks_history_pipeline` 的 ThreadPoolExecutor 并发骨架**遍历 close_series 的 5531 code，产出：
  ```json
  { "schema_version": "1.0", "generated_at": "...", "source": "cninfo",
    "map": { "600519": {"l1": "饮料", "l2": "白酒"}, ... },
    "unmapped": ["...无巨潮归属的 code..."] }
  ```
- 低频刷新（月级，成分变动慢），独立于日更热路径。
- **韧性**：并发 + 单股重试；**持久缓存 + 断点续跑**（合并本次成功 + 上次 good map），任何规模失败都不产出空 map、不阻断下游。覆盖率 <阈值则告警但仍用旧 map。

### 2.3 宽度计算（新增核心，纯函数）
- `src/market_breadth/self_breadth.py`：
  - 入参：close_series（dates + {code: [close...]}）、stock_industry_map、periods=[20,60,120]。
  - 逐股逐日：`sma = mean(close[i-n+1 : i+1])`（窗口不足 n → 该日该股无 SMA，不计入）；`above = close[i] > sma`。
  - **有效样本**：该股该日 close 非 null 且已有 n 日历史。分母只含有效样本。
  - 聚合（每周期，均按 `sum(above)/sum(valid)×100` 逐日成序列，**真·个股占比**）：
    - 全市场：全体有效个股。
    - 二级行业：按 `industry_map[code].l2`（巨潮行业中类）分组。
    - 一级行业：按 `industry_map[code].l1`（巨潮行业大类）分组——**直接个股级聚合**，非二级率再平均。
    - 无归属个股（不在 map）：计入全市场，不计入任何行业。
  - 输出结构见 2.4。
- 计算量：5531 股 × 150 日 × 3 周期，滚动均值可 O(n) 前缀和；纯 Python 亦可秒级，无需 numpy 强依赖（若已有 pandas 可用则用）。

### 2.4 快照 schema 2.0（`market_temperature.json`）
```json
{
  "schema_version": "2.0",
  "generated_at": "...", "source": "self", "metric": "maN_above_ratio",
  "dates": ["...150 或截断展示 ~60 交易日..."],
  "periods": {
    "ma20": { "market": [{ "date","rate" }], "industries_l1": [BreadthRow], "industries_l2": [BreadthRow] },
    "ma60": { ... },
    "ma120": { ... }        // 历史不足时 market/latest 可为 null, 前端提示
  }
}
```
- `BreadthRow` 沿用现结构 `{name, l1?, series, latest}`。
- 展示窗口：dates 全量 150 供 series，但热力图可只画最近 ~60 列（避免过宽）；由前端截取，快照给全量。
- **兼容**：schema 1.0（dapanyuntu 单周期）→ 2.0。前端按 `schema_version`/`periods` 存在性分支；旧快照无 periods 时退化为 MA20 单档只读。

### 2.5 dapanyuntu 对账（保留 + 新增 QC，**仅全市场**）
- 继续跑 `market_breadth/pipeline.py`（dapanyuntu），输出改到 `market_breadth_qc_dapanyuntu.json`（不再当主展示）。
- 新增 `src/market_breadth/reconcile.py`：**仅全市场**——自算全市场 MA20 vs dapanyuntu 各行业 MA20 的等权均值（dapanyuntu 的全市场口径），产出 `market_breadth_qc.json`：
  ```json
  { "date", "market_self_ma20", "market_dapanyuntu", "abs_diff", "over_threshold": bool }
  ```
- **行业级不对账**（巨潮 vs 东财 taxonomy 不同源，非 apples-to-apples）。
- 阈值：首跑据实定（预期个位数百分点，方法学差异）；超阈 warning，不阻断。

### 2.6 编排接入
- `cn-refresh.yml`：现有 dapanyuntu step 之后，追加：self_breadth 计算（读 close_series+map）→ reconcile。均 `continue-on-error`，失败保留上一份。
- 映射刷新：独立低频 workflow（或 backfill 里附带），不进日更热路径。
- 归档：`archiver.py` FILES 已白名单化，追加 `market_breadth_qc.json`；`market_temperature.json` 已在。

## 3. 前端

### 3.1 数据层
- `types/marketTemperature.ts`：schema 2.0（`periods` 嵌套），保留 1.0 兼容解析。
- `hooks/useMarketTemperature.ts`：不变 URL；解析后暴露 `periods` + 可用周期列表（MA120 可能缺）。

### 3.2 组件
- `TemperaturePage.tsx`：新增全局 `period: 'ma20'|'ma60'|'ma120'` 状态 + 切换器（MA120 不可用时禁用+提示）；把选中周期的 `{market, industries_l1, industries_l2}` 下发给现有三组件（**组件签名基本不变**，复用 BreadthThermometer/IndustryBreadthRanking/BreadthHeatmap）。
- 口径文案：改为「全市场/行业为**个股**站上 SMA_n 的真实占比；停牌与上市不足 N 日的新股不计入」。

## 4. 关键取舍

| 取舍 | 选择 | 理由 |
|---|---|---|
| 数据源 | 自建为主 + dapanyuntu 全市场对账 | 多周期只能自建；东财 CI 0/5 死，巨潮唯一可用 |
| 行业分类 | 巨潮（大类/中类） | 东财/申万 CI 不可用；巨潮逐股稳，层级自带、映射与体系一次到手 |
| 全市场口径 | 真·个股占比 | 有个股后消除等权近似，修正原页面注意事项 |
| 一级聚合 | 成分股合并再算 | 比「二级率再平均」更准（大小行业不等权） |
| schema | 单文件多周期嵌套 | 前端一次 fetch，切换零延迟 |
| MA120 历史 | backfill 到 150 + daily 同步 | 零成本加深；不改则 daily 截回 75 |

## 5. 兼容性 / 回滚

- 页面主数据从 dapanyuntu 切到自建：若自建管线失败，`market_temperature.json` 保留上一份；极端回滚可临时切回 dapanyuntu 输出（改一处 URL/文件名）。
- schema 2.0 前端向后兼容 1.0，历史旧快照不报错。
- 回滚点：映射 spike / 计算 / 前端 各自独立可退。

## 6. 测试策略

- 纯函数 `self_breadth`：构造小矩阵，验证 SMA、站上、新股(历史不足)/停牌(null)排除、全市场占比、一级成分合并聚合、多周期。
- reconcile：构造自算 vs dapanyuntu，验证偏差与超阈标记。
- 映射管线：mock 接口，验证反转 + 未归属收集。
- 前端：schema 2.0 解析、周期切换联动、MA120 缺失禁用提示、1.0 兼容。

## 7. 拆分建议（可选）

体量偏大，可拆父子任务：①历史加深+映射管线 ②宽度计算+schema ③对账QC ④前端多周期。各自独立可验。若单人顺序推进，用本 implement.md 的里程碑即可，不强制拆。
