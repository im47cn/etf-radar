# 主题下钻成分股 Phase 2 设计稿（个股技术指标）

- **日期**：2026-06-25
- **作者**：im47cn / Claude
- **状态**：设计已通过头脑风暴评审，待写入实施计划
- **关联**：[2026-06-23 theme-stocks-phase-1-design](./2026-06-23-theme-stocks-phase-1-design.md)

---

## 1. 背景与目标

### 1.1 背景
- Phase 1 已上线主题成分股页面，仅展示价格 / 涨跌（信息密度低，无法支持研判决策）
- 用户需在「主题 → ETF → 成分股」链路上完成 **3 个核心场景**：
  1. **挑选龙头**：从 10 只重仓股里快速识别本主题最强的个股
  2. **结构诊断**：判断主题是「头部带动 / 全面强势 / 分化」三种结构之一
  3. **持仓择时**：已持有该主题股票时，决定加仓 / 减仓 / 观望

### 1.2 目标（Phase 2 — MVP）
1. 为 holdings 涉及的 ~101 只 A 股个股提供 4 个核心指标：**60 日强度 / 20 日强度 / RSI(14) / 量比**
2. 龙头规则自动标注（⭐⭐⭐ / ⭐⭐ / ⭐ / 无），默认按龙头 + 强度排序
3. 表格行支持 hover 弹出 **60 日 K 线小图**（OHLC，SVG 原生绘制，无库依赖）
4. 主题结构诊断摘要（一行文案 + 强度直方图缩略）
5. CI：一次性 backfill + 工作日盘后增量 daily pipeline

### 1.3 非目标
- 个股 MACD / KDJ / 布林带（YAGNI，4 个指标已覆盖 3 个场景）
- 全 A 股池筛选（仅限 holdings 涉及的 ~101 只）
- 美股个股指标（→ Phase 3，需先抓美股 holdings）
- 个股基本面（市值 / ROE / 估值）（→ Phase 3）
- 个股 → 主题反向链路 / 多主题归属（独立 issue）
- 实时盘中刷新指标（指标按日终一次性计算即可，不进 spot 30min 链路）

---

## 2. 架构总览

```
后端
├── 季度管道 holdings_pipeline (Phase 1 已上线)
├── 盘中管道 stocks_spot_pipeline (Phase 1 已上线，每 30 min)
├── 一次性 stocks_history_pipeline (workflow_dispatch only)
│   └── akshare stock_zh_a_hist × 5000 股票 × 75 日 → 全市场基线
│       └─→ data/stocks/close_series.json  (backend-only)
│       └─→ data/stocks/volume_series.json (backend-only)
│       └─→ data/stocks/ohlc/{code}.json   × ~101 个 holdings 股
└── 日频管道 stocks_daily_pipeline (BJT 16:30 cron, 工作日)
    ├── 拉今日 spot → append 到 close/volume_series（保留尾部 75 行）
    ├── 全市场批量算 r_5d/r_20d/r_60d → 算每只 holdings 股的 60d/20d 强度
    ├── 算 RSI(14) / 量比 / 龙头标签
    └── 写 data/stocks/holdings_indicators.json + ohlc/{code}.json

前端
├── 扩展 StockTable：加 leader / strength / RSI / volRatio 4 列
├── 新组件 MiniKlineChart (SVG 原生 60 日 OHLC)
├── 新组件 ThemeStructureSummary
├── 新 hooks useStockIndicators + useStockOhlc (lazy on hover)
└── 新模块 lib/stocks/indicatorThresholds + structureInsight + leaderRule
```

### 关键决策

| 决策 | 原因 |
|---|---|
| 全 A 股池算强度（非主题内池） | 语义最绝对：「这只股在全市场 5000 只里排前 X%」比「在主题 10 只里排第 N」更可解释 |
| backfill + daily 增量（非每日全量） | 全量 fetch 5000 股 × 75 日太重，每日仅增量 1 日 spot |
| close_series / volume_series 仅后端使用，不进前端 | 前端只需 ~101 个股的预算好的 indicator，避免 3-4 MB 包体 |
| 60 日 OHLC 单股一文件 | 仅 ~101 文件、~3-6 KB / 文件，lazy load on hover，零初始包体 |
| 跨主题股不做全局去重 | 实测仅 9 只跨主题股，去重逻辑工程复杂度不值得；输出 Dict 自然去重 |
| 龙头规则只用 strength + RSI（不用量比） | 量比是单日噪声，不该入选长期判定；仅作辅助列 |
| RSI 用第三方库 `ta`（非自实现） | Wilder's smoothing 边界条件多，库已验证；ta 比 ta-lib 无系统依赖更轻 |
| 强度计算用 `scipy.stats.rankdata` + numpy 向量化 | 避免 5000² 复杂度；实测 20-40 ms |
| backfill 并发 4（非 8） | akshare 实测安全上限 3-5；超阈自动切前/后半场分片 |
| K 线小图 SVG 原生（非 chart 库） | 60 个 path 元素 << recharts 启动开销；移动端隐藏 |
| 强度评分集成进现有 strength.py | 单一源解释（ETF 双轨强度复用） |

---

## 3. 数据契约

### 3.1 `data/stocks/close_series.json`（backend-only，每日 append）

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-25T08:30:00+00:00",
  "dates": ["2026-03-31", "2026-04-01", "..."],
  "stocks": {
    "002129": [12.5, 12.6, null, "..."],
    "603501": [98.7, 99.1, 100.2, "..."]
  }
}
```

**字段说明**：
- `dates`：长度恒定为 75（≥ 60 日指标 + 15 日 buffer）
- `stocks[code]`：与 `dates` 同长度的收盘价数组；停牌 / 上市前为 `null`
- 文件估算：5000 股 × 75 日 × ~8 byte ≈ 3 MB（gzip 后约 500 KB）
- **不直接 deploy 给前端**（在 `deploy-frontend.yml` paths 中显式排除）

### 3.2 `data/stocks/volume_series.json`（backend-only，每日 append）

结构同 3.1，`stocks[code]` 为成交量数组（单位：股）。文件估算 ~1 MB。

### 3.3 `data/stocks/holdings_indicators.json`（前端读取）

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-25T08:30:00+00:00",
  "stocks": {
    "002129": {
      "name": "TCL中环",
      "strength_60d": 87,
      "strength_20d": 91,
      "rsi_14": 62.3,
      "vol_ratio": 1.85,
      "leader": "⭐⭐"
    },
    "603501": {
      "name": "韦尔股份",
      "strength_60d": 94,
      "strength_20d": 88,
      "rsi_14": 68.1,
      "vol_ratio": 2.4,
      "leader": "⭐⭐⭐"
    }
  }
}
```

**字段说明**：
- `stocks` 为对象（按 code 查询），仅含 holdings 涉及个股（实测 ~101 只）
- `strength_60d` / `strength_20d`：0-99 整数（缺失数据为 `null`）
- `rsi_14`：浮点 1 位小数，0-100；不足 15 个交易日为 `null`
- `vol_ratio`：今日量 / 过去 5 日均量；停牌 / 不足天数为 `null`
- `leader`：枚举 `"⭐⭐⭐" | "⭐⭐" | "⭐" | ""`（空字符串表无标记）
- 文件估算：~101 股 × 6 字段 ≈ 30-50 KB

### 3.4 `data/stocks/ohlc/{code}.json`（前端 lazy load）

```json
{
  "code": "002129",
  "name": "TCL中环",
  "generated_at": "2026-06-25T08:30:00+00:00",
  "bars": [
    { "date": "2026-04-01", "o": 12.30, "h": 12.65, "l": 12.20, "c": 12.50, "v": 5230000 },
    "..."
  ]
}
```

- `bars` 长度 ≤ 60；停牌日不写入
- 单文件 3-6 KB；总数 ≤ 200（含轮换历史）

### 3.5 `data/stocks/index.json`（索引）

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-25T08:30:00+00:00",
  "ohlc_codes": ["002129", "603501", "..."],
  "last_trade_date": "2026-06-25"
}
```

---

## 4. 后端设计

### 4.1 数据模型扩展（`backend/src/models.py`）

```python
class StockIndicators(BaseModel):
    name: str
    strength_60d: int | None
    strength_20d: int | None
    rsi_14: float | None
    vol_ratio: float | None
    leader: str  # "⭐⭐⭐" | "⭐⭐" | "⭐" | ""

class StockOhlcBar(BaseModel):
    date: date
    o: float
    h: float
    l: float
    c: float
    v: int

class StockOhlc(BaseModel):
    code: str
    name: str
    generated_at: datetime
    bars: list[StockOhlcBar]  # len ≤ 60
```

### 4.2 强度评分改造（`backend/src/scoring/strength.py`）

新增向量化批量函数（避免 5000² 复杂度）：

```python
import numpy as np
from scipy.stats import rankdata

def batch_strength_per_dim(
    returns_array: np.ndarray,
    k: float,
    days_in_dim: int,
) -> np.ndarray:
    """
    向量化版本：5000 只股一次性算百分位 + 动量。
    输入：长度 N 的全市场收益数组（含 NaN）
    输出：长度 N 的强度数组（0-99，NaN 保持 NaN）
    """
    n = len(returns_array)
    valid_mask = ~np.isnan(returns_array)
    n_valid = int(valid_mask.sum())

    # 百分位（仅在有效值内排名，scipy.rankdata 用 average 处理并列）
    P = np.full(n, np.nan)
    if n_valid > 0:
        ranks = rankdata(returns_array[valid_mask], method='average')
        P[valid_mask] = (ranks / n_valid) * 100

    # 动量 sigmoid
    annualized = returns_array * (252 / days_in_dim)
    M = 100.0 / (1.0 + np.exp(-k * annualized))

    raw = 0.5 * P + 0.5 * M
    score = np.clip(np.round(raw), 0, 99)
    score[np.isnan(raw)] = np.nan
    return score
```

**等价性测试**：与原 `strength_per_dim(own, pool)` 逐元素对比，最大误差 ≤ 1（round 之后允许 ±1 误差）。

### 4.3 个股指标计算（`backend/src/scoring/stock_indicators.py`，新增）

```python
import pandas as pd
from ta.momentum import RSIIndicator

def compute_rsi(closes: list[float | None], period: int = 14) -> float | None:
    """Wilder's RSI(14)，使用 ta 库。不足 period+1 个有效收盘价时返回 None。"""
    series = pd.Series(closes).dropna()
    if len(series) < period + 1:
        return None
    rsi = RSIIndicator(close=series, window=period, fillna=False).rsi()
    last = rsi.iloc[-1]
    return None if pd.isna(last) else round(float(last), 1)

def compute_volume_ratio(volumes: list[int | None]) -> float | None:
    """A 股标准量比：今日量 / 前 5 个交易日均量。"""
    if len(volumes) < 6 or volumes[-1] is None:
        return None
    prev_5 = [v for v in volumes[-6:-1] if v is not None and v > 0]
    if len(prev_5) < 5:
        return None
    mean_prev = sum(prev_5) / 5
    if mean_prev <= 0:
        return None
    return round(volumes[-1] / mean_prev, 2)
```

### 4.4 龙头规则（`backend/src/scoring/leader_rule.py`，新增）

```python
def classify_leader(strength_60d: int | None, rsi_14: float | None) -> str:
    """
    龙头标签（仅作提示，不替代用户判断）。
    返回字符串："⭐⭐⭐" / "⭐⭐" / "⭐" / ""
    """
    if strength_60d is None:
        return ''
    if rsi_14 is None:
        return '⭐' if strength_60d >= 70 else ''
    if strength_60d >= 90 and 50 <= rsi_14 <= 70:
        return '⭐⭐⭐'
    if strength_60d >= 80 and 45 <= rsi_14 <= 70:
        return '⭐⭐'
    if strength_60d >= 70:
        return '⭐'
    return ''
```

**为什么不引入量比作为龙头条件**：量比是单日异动指标（噪声），将其作为长期"龙头"标签的入选条件会带来高假阳性。量比仅以独立列展示，由用户自行解读。

### 4.5 一次性历史回填管道（`backend/src/stocks_history_pipeline.py`，新增）

**入口**：
```bash
uv run python -m src.stocks_history_pipeline --days 75 [--max-workers 4] [--force-shard]
```

**步骤**：
1. 通过 `ak.stock_zh_a_spot_em()` 拉全市场股票列表（~5000 只）
2. **并发抓取**：`max_workers=4`（akshare 实测安全上限）+ 指数退避（0.5s, 1s, 2s, 4s, max 3 retries）
3. **失败率自适应**：累计失败率 > 15% 自动切到分片模式（前 2500 → sleep 30min → 后 2500）
4. **断点续传**：每 500 股 checkpoint 写 `data/stocks/_checkpoint.json`；中断后跳过已成功的
5. 汇总写：
   - `data/stocks/close_series.json`（5000 股 × 75 日）
   - `data/stocks/volume_series.json`
   - `data/stocks/ohlc/{code}.json`（仅 holdings 涉及的 ~101 只，60 bars）
   - `data/stocks/index.json`

**预计耗时**：4 并发 → 5-8 分钟；分片模式 → 35-40 分钟（含 sleep）

### 4.6 日频增量管道（`backend/src/stocks_daily_pipeline.py`，新增）

**入口**：
```bash
uv run python -m src.stocks_daily_pipeline
```

**步骤**：
1. 读取 `data/stocks/close_series.json` 与 `volume_series.json`
2. 通过 `ak.stock_zh_a_spot_em()` 拉今日全市场 close + volume
3. **append + truncate**：所有股票数组追加今日一格，掐头保留尾部 75 行
4. **批量算全市场强度**：
   - 提取每只股的 r_60d = (close[-1] - close[-61]) / close[-61]，r_20d 同理
   - 调用 `batch_strength_per_dim(r_60d_array, k=K_60, days_in_dim=60)` 得 5000 个强度
   - 同理算 strength_20d
5. **遍历 holdings 涉及个股**（约 101 个 unique codes，跨主题股自然去重）：
   - 查表取该股的 strength_60d / strength_20d
   - 用 `compute_rsi(close[-15:])` 算 RSI(14)
   - 用 `compute_volume_ratio(volume[-6:])` 算量比
   - 用 `classify_leader(strength_60d, rsi_14)` 算龙头标签
6. 写：
   - `data/stocks/close_series.json`（覆盖）
   - `data/stocks/volume_series.json`（覆盖）
   - `data/stocks/holdings_indicators.json`（覆盖，**写入前 numpy NaN → Python None，int 字段强制转 `int | None`**）
   - `data/stocks/ohlc/{code}.json`（仅 holdings 个股，60 bars 截窗）
   - `data/stocks/index.json`（更新 last_trade_date）

**预计耗时**：单 spot 调用 + 批量计算 ≈ 30-60 秒

### 4.7 Provider 扩展（`backend/src/providers/stock_history_provider.py`，新增）

```python
class StockHistoryProvider:
    def fetch_history(self, code: str, days: int) -> list[StockOhlcBar]:
        """
        Wraps ak.stock_zh_a_hist。
        - symbol 编码：A 股 6 位，深交所 'sz' 沪 'sh'（akshare 自动判断）
        - 北交所 'bj' 前缀仅当 code 以 8/4 开头时
        - 失败抛 StockHistoryFetchError
        """
```

---

## 5. 前端设计

### 5.1 类型定义（`frontend/src/types/stockIndicators.ts`，新增）

```typescript
export interface StockIndicators {
  name: string;
  strength_60d: number | null;
  strength_20d: number | null;
  rsi_14: number | null;
  vol_ratio: number | null;
  leader: '⭐⭐⭐' | '⭐⭐' | '⭐' | '';
}

export interface StockOhlcBar {
  date: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface StockOhlc {
  code: string;
  name: string;
  generated_at: string;
  bars: StockOhlcBar[];
}

export interface AggregatedStock {
  code: string;
  name: string;
  weight_sum: number;        // Phase 1 字段
  etfs: string[];             // Phase 1 字段
  close: number | null;       // Phase 1 字段
  r_1d: number | null;        // Phase 1 字段
  indicators?: StockIndicators;  // Phase 2 新增（lazy join）
}
```

### 5.2 新 Hooks

**`frontend/src/lib/holdings/useStockIndicators.ts`**：
- 启动时 fetch `holdings_indicators.json` 一次
- 返回 `Map<code, StockIndicators>`，404 时返回空 Map

**`frontend/src/lib/holdings/useStockOhlc.ts`**：
- 接受 `code: string | null`，code 为 null 时不 fetch
- fetch `data/stocks/ohlc/{code}.json`，模块内 Map 缓存
- 返回 `{ data, loading, error }`

### 5.3 表格扩展（`frontend/src/components/stocks/StockTable.tsx`）

新增 4 列（位于 Phase 1 列右侧）：

| 列 | 显示 | 排序 |
|---|---|---|
| 龙头 | `leader` 字符串 | 是（⭐⭐⭐ > ⭐⭐ > ⭐ > ''） |
| 60d 强度 | `<StrengthBadge value={strength_60d} />` | 是 |
| 20d 强度 | `<StrengthBadge value={strength_20d} />` | 是 |
| RSI | `<RSIBadge value={rsi_14} />` | 是 |
| 量比 | `<VolumeRatioBadge value={vol_ratio} />` | 是 |

**默认排序**：`leader desc → strength_60d desc`（自动把龙头顶到表头）

**hover 交互**：行 hover 时显示 `<MiniKlineChart code={code} />` 浮层（绝对定位，仅桌面端 `md` breakpoint 以上启用）

### 5.4 新组件

**`frontend/src/components/stocks/MiniKlineChart.tsx`**（SVG 原生）：
- props: `code: string`
- 内部 lazy fetch OHLC，宽 160px × 高 80px
- 渲染 60 根 K 线（红涨绿跌），open/close 实心矩形 + high/low 影线
- bars 长度 < 5 时显示「数据不足」

**`frontend/src/components/stocks/StrengthBadge.tsx` / `RSIBadge.tsx` / `VolumeRatioBadge.tsx`**：
- 各自 30-50 行的展示组件
- 阈值颜色映射从 `lib/stocks/indicatorThresholds.ts` 读取

**`frontend/src/components/stocks/ThemeStructureSummary.tsx`**：
- 在 StocksPage 顶部，StockTable 上方
- 显示一行文案（来自 `lib/stocks/structureInsight.ts`）+ 强度直方图缩略 SVG
- 单独显示「本主题 ⭐⭐⭐ 个数 / 占比」

### 5.5 集中阈值与解读（避免散在组件里）

**`frontend/src/lib/stocks/indicatorThresholds.ts`**：

```typescript
export const STRENGTH_TIERS = [
  { min: 90, label: '极强', color: 'bg-red-100 text-red-700' },
  { min: 80, label: '强', color: 'bg-orange-100 text-orange-700' },
  { min: 60, label: '中性', color: 'bg-gray-100 text-gray-600' },
  { min: 40, label: '偏弱', color: 'bg-blue-100 text-blue-700' },
  { min: 0,  label: '弱', color: 'bg-blue-200 text-blue-800' },
];

export const RSI_ZONES = {
  overbought: 70,    // 警示
  bullish_top: 65,
  bullish_bottom: 50,
  oversold: 30,
};

export const VOL_RATIO_THRESHOLDS = {
  high: 2.0,         // 显著放量
  low: 0.5,          // 显著缩量
};
```

**`frontend/src/lib/stocks/structureInsight.ts`**：

```typescript
export type ThemeStructure = 'head_led' | 'broad_strength' | 'divergent' | 'weak';

export function diagnoseStructure(
  stocks: AggregatedStock[],
): { type: ThemeStructure; text: string } {
  // rule 1: 仅 1-2 只 strength_60d ≥ 80 → 头部带动
  // rule 2: ≥ 6 只 strength_60d ≥ 70 → 全面强势
  // rule 3: 强度方差大 + 没有明显头部 → 分化
  // rule 4: 均值 < 50 → 主题整体偏弱
}
```

输出 4 种文案：
- "本主题由 X 龙头带动，其他成分股偏中性"
- "本主题 X 只股票强度 ≥ 70，全面走强"
- "本主题强度分化（头部 X 尾部 Y），结构不健康"
- "本主题整体偏弱（均值 X），建议观望"

### 5.6 数据流变更（`frontend/src/lib/holdings/aggregator.ts`，扩展）

`aggregateHoldingsWithSpot()` 增参数 `indicators: Map<code, StockIndicators>`，输出 `AggregatedStock[]` 时 join `indicators[code]` 到 `.indicators` 字段（缺失允许 undefined，表格显示「—」）。

---

## 6. CI / 测试 / 风险

### 6.1 CI Workflows

**`.github/workflows/stocks-history-backfill.yml`**（仅手动触发）：

```yaml
on:
  workflow_dispatch:
    inputs:
      days: { default: '75' }
      max_workers: { default: '4' }
      force_shard: { default: 'false' }
permissions: { contents: write }
concurrency: { group: stocks-history-backfill }
timeout-minutes: 45
```
跑 `stocks_history_pipeline` → commit `data/stocks/` → push。

**`.github/workflows/stocks-daily.yml`**（工作日盘后）：

```yaml
on:
  schedule:
    - cron: '30 8 * * 1-5'   # UTC 08:30 = BJT 16:30
  workflow_dispatch:
permissions: { contents: write }
concurrency: { group: stocks-daily }
```
跑 `stocks_daily_pipeline` → commit `data/stocks/holdings_indicators.json` + `ohlc/` + `index.json` + `close_series.json` + `volume_series.json` → push。

**`.github/workflows/deploy-frontend.yml` 调整**：在 `on.push.paths` 中**显式排除** backend-only 文件，避免无意义部署：

```yaml
on:
  push:
    branches: [main]
    paths:
      - 'data/**'
      - 'frontend/**'
      - '!data/stocks/close_series.json'
      - '!data/stocks/volume_series.json'
```

### 6.2 测试策略

**Backend（新增 4 测试文件 / ~25 用例）**

| 文件 | 覆盖 |
|---|---|
| `test_strength_batch_equivalence.py` | `batch_strength_per_dim` vs `strength_per_dim` 逐元素等价（误差 ≤ 1）；NaN 传播；空数组；全相等数组 |
| `test_stock_indicators.py` | RSI 已知数列回归；量比标准定义；停牌 / 不足天数 / 零均量 → None |
| `test_leader_rule.py` | 6 个边界（90+RSI 65 / 90+RSI 75 / 85+RSI 60 / 70+RSI None / 65+RSI 60 / 边界值 80,50,70） |
| `test_stocks_daily_pipeline.py` | mock spot + 既有 close_series → 验证 append / truncate-75 / 输出契约 |

**Frontend（新增 6 测试文件 / ~30 用例）**

| 文件 | 覆盖 |
|---|---|
| `useStockIndicators.test.ts` | fetch 成功 / 404 / 空对象 |
| `useStockOhlc.test.ts` | code null 不 fetch；hover 触发；模块缓存复用 |
| `MiniKlineChart.test.tsx` | SVG snapshot（60 bars / 空数据 / 单日数据）；红绿色判定 |
| `ThemeStructureSummary.test.tsx` | 4 种 rule 触发文案；无数据回退 |
| `structureInsight.test.ts` | 阈值边界 / 多 rule 优先级 |
| `StockTable.test.tsx`（扩展） | 新增 4 列渲染；徽章颜色映射；缺失 indicators 占位；龙头默认排序 |

**契约测试**：`backend/tests/test_output_schemas.py` 追加 4 个 schema（`HoldingsIndicators` / `StockOhlc` / `StockCloseSeries` / `StocksIndex`），pydantic round-trip 校验。

### 6.3 风险登记表

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | akshare 限频 / 熔断（5000 次 backfill） | **高** | 4 并发 + 指数退避 + checkpoint；失败率 > 15% 自动切前/后半场分片 |
| R2 | 新股 < 75 天 / 停牌 / 退市 | 中 | indicators 设 None，前端显示「—」；退市股每周扫一次 close_series 清理 |
| R3 | close_series / volume_series 文件膨胀 | 中 | 严格截窗 75 行；commit 前 size check（> 5 MB 告警） |
| R4 | daily pipeline 每天触发 deploy（~14 次 spot + 1 次 daily ≈ 15 次/天） | 低 | deploy-frontend.yml paths 排除 backend-only 文件；可承受 |
| R5 | 移动端 K 线小图渲染过慢 | 低 | 仅桌面端 hover 触发；移动端折叠隐藏；SVG ≤ 60 path 元素 |
| R6 | ta 库版本兼容（pandas 2.x） | 低 | uv lock 钉版本；纳入 dependabot 监控 |
| R7 | 首次 backfill commit 体积大（~5 MB JSON） | 低 | 一次性接受；后续 daily 增量 commit ≤ 200 KB |
| R8 | 全市场 r_5d / r_20d / r_60d 拉取失败导致强度回退 | 中 | 拉不到时跳过 indicators 更新（保留昨日数据），不写空文件覆盖 |

### 6.4 Phase 2 上线 Checklist

```
[ ] backend tests 全绿 (uv run pytest)
[ ] frontend tests 全绿 (npx vitest run)
[ ] 本地跑通 stocks_history_pipeline (一次性, --days 75)
[ ] 本地跑通 stocks_daily_pipeline (mock spot)
[ ] deploy-frontend.yml paths 排除 close_series/volume_series 已合入
[ ] 手动触发 stocks-history-backfill workflow (生产首次)
[ ] 验证 data/stocks/ 产物 commit + push
[ ] 手动触发 stocks-daily workflow 验证完整链路
[ ] 等待自然 cron (BJT 16:30) 跑通一次
[ ] 前端线上验证：StocksPage 显示新 4 列 + hover K 线 + 结构摘要
[ ] grep themes.yml 跨主题股数量 ≤ 20（如远超，重新评估去重策略）
[ ] backfill 首次跑失败率 ≤ 5%
[ ] 监控 1 周：akshare 失败率 / deploy 次数 / Pages 流量
[ ] 龙头标记上线 1 周后用户反馈：⭐⭐⭐ 命中率是否符合直觉
```

---

## 7. 后续 Phase 预留

- **Phase 3**：个股基本面（市值 / ROE / PE 分位）、美股 holdings、龙头规则升级（加入基本面因子）
- **Phase 4**：个股 → 主题反向链路（点击个股查所属主题）、多主题归属可视化
- **Phase 5**：自定义指标 / 自定义龙头规则配置面板

---

## 8. 验收标准

1. 任一 A 股主题成分股页面显示新 4 列（leader / 60d 强度 / 20d 强度 / RSI / 量比），且龙头默认置顶
2. 行 hover 在 200ms 内显示 60 日 K 线小图（桌面端）
3. 主题结构摘要文案与肉眼判断一致（4 种 rule 至少各命中 1 个主题）
4. 工作日盘后 30 min 内 holdings_indicators.json 更新（cron 触发 + commit + deploy 完成）
5. 跨主题股（如 600519）在两个主题页面显示完全相同的指标数据
6. backfill 失败率 ≤ 5%；daily pipeline 失败率 ≤ 2%
