# ETF Radar — 跨市场主题联动分析平台 设计文档

> 版本: 1.0
> 日期: 2026-06-05
> 状态: 待审阅
> 来源: 基于 `docs/htsc-us-cn-linkage-product-doc.md` + `docs/htsc-us-cn-linkage-requirements.md` 头脑风暴产出

---

## 0. 文档导览

| 章节 | 内容 | 适合谁先看 |
|------|------|----------|
| 1 | 系统架构总览 | 所有人 |
| 2 | 数据层 (调度/Provider/ETL/容灾) | 后端/DevOps |
| 3 | 算法层 (强度/映射/信号 公式) | 算法/后端 |
| 4 | 数据模型 (JSON Schema) | 前后端契约 |
| 5 | 前端架构 (组件/状态/部署) | 前端 |
| 6 | 收尾 (目录/错误/测试/监控) | 所有人 |
| 附录 A | 决策摘要 (Q1-Q9) | 评审 |
| 附录 B | 显式不做的事 (YAGNI) | 评审 |
| 附录 C | 与原需求文档的偏差说明 | 评审/产品 |
| 附录 D | 未来路线图 | 产品 |

---

## 1. 系统架构总览

### 1.1 整体架构图

```
                       GitHub Actions (调度层)
        ┌──────────────────┬──────────────────┬──────────────────┐
        │ US Refresh       │ CN Refresh       │ Frontend Deploy  │
        │ (06:30 北京 cron) │ (09:15 + 15min)  │ (push 后自动)    │
        └────────┬─────────┴────────┬─────────┴──────────┬───────┘
                 ▼                  ▼                    │
        ╔════════════════════════════════════════╗       │
        ║       backend/ (Python Pipeline)        ║       │
        ║  ┌──────────────────────────────────┐  ║       │
        ║  │ providers/   (yfinance/akshare)  │  ║       │
        ║  │      ↓                            │  ║       │
        ║  │ scoring/  (strength/mapping/sig) │  ║       │
        ║  │      ↓                            │  ║       │
        ║  │ pipeline.py  (orchestrator)      │  ║       │
        ║  └────────────────┬─────────────────┘  ║       │
        ╚═══════════════════╪══════════════════════╝       │
                            ▼                              │
        ╔══════════════════════════════════════╗           │
        ║          data/ (git tracked)          ║           │
        ║  latest/{themes,etfs,signals,meta}    ║           │
        ║  snapshots/2026-06-05/{...4 files}    ║           │
        ╚══════════╦═══════════════════════════╝           │
                   │  fetch('/data/latest/*')              │
                   ▼                                       ▼
        ┌──────────────────────────────────────────────────────┐
        │            frontend/ (React + Vite SPA)               │
        │  ─ KpiCards  ─ FilterBar  ─ ThemeList                 │
        │  ─ ThemeDetail (Recharts 环形图)                       │
        │  ─ CnEtfTable                                          │
        └────────────────────────────────────────────────────────┘
                                ▲
                        GitHub Pages (gh-pages 分支)
                                ▲
                              浏览器
```

### 1.2 分层职责

| 层 | 职责 | 物理位置 | 何时跑 |
|----|------|---------|------|
| 调度层 | 触发数据刷新与前端部署 | `.github/workflows/*.yml` | cron + push |
| 数据获取层 | 从外部 API 拉行情 | `backend/providers/` | 调度触发 |
| 计算层 | 算强度/映射/信号 | `backend/scoring/` | 调度触发 |
| 数据持久层 | JSON 写入 git | `data/latest/`, `data/snapshots/` | 调度触发 |
| 展示层 | 渲染 UI | `frontend/` build 到 GitHub Pages | 浏览器加载时 |

### 1.3 关键设计原则

1. 后端只输出 JSON, 不暴露 HTTP API — 零服务器
2. 前端是纯静态 SPA, 所有数据来自 git 中的 JSON 文件
3. 算法在 Python 端跑, 前端不重算 — 前端只做渲染和筛选
4. 配置 (themes.yml) 与代码同仓 — 改主题映射 = 改文件 + commit
5. 状态在 git 历史里 — 不需要数据库

---

## 2. 数据层

### 2.1 调度层 — 四个 GitHub Actions Workflow

| Workflow 文件 | cron (UTC) | 北京时间 | 任务 |
|--------------|-----------|---------|------|
| `us-refresh.yml` | `30 22 * * 1-5` | 工作日 06:30 | 拉美股 ETF 全部周期 → 算美股主题强度 → 重算所有信号 |
| `cn-refresh.yml` (全量) | `15 1 * * 1-5` | 09:15 | 拉 A 股 ETF → 算 A 股 ETF 强度 → 重算信号 |
| `cn-refresh.yml` (盘中刷价 上午) | `*/15 1-3 * * 1-5` | 09:15-11:45 每 15min | 仅 intraday 模式刷价 |
| `cn-refresh.yml` (盘中刷价 下午) | `*/15 5-7 * * 1-5` | 13:15-15:45 每 15min | 仅 intraday 模式刷价 |
| `cn-eod-archive.yml` | `30 7 * * 1-5` | 工作日 15:30 | A 股收盘后将 `latest/` 复制到 `snapshots/<today>/` |
| `deploy-frontend.yml` | `push: paths: [frontend/**, data/**]` | — | 构建前端 + 部署到 `gh-pages` 分支 |

> **避开 A 股午休时段** (11:30-13:00, 即 UTC 03:30-05:00): 用两段 cron 表达式分别覆盖上下午, 节省约 8 次/天无意义调度。

**关键设计: 盘中 15min 刷新只跑"轻量分支"**

```python
# pipeline.py 用 --mode 区分
python -m backend.pipeline --mode=full     # 全量重算 (全部周期 + 信号)
python -m backend.pipeline --mode=intraday # 仅刷 A 股最新价格 + 信号方向重判
python -m backend.pipeline --mode=archive  # latest → snapshots/<date>/ 复制
```

`intraday` 模式跳过 60/120/YTD 长周期计算 (盘中不变), 耗时 < 30 秒, 节省 Actions 额度。

> **intraday 模式下的字段处理约定**:
> - `r_1d`, `r_5d`, `price`, `amount_yi` → **盘中每次更新**
> - `r_20d`, `r_60d`, `r_120d`, `r_ytd` → 沿用早 09:15 全量计算结果, 不重算 (盘中漂移可忽略)
> - `strength.short` → 每次刷新重算 (依赖 r_1d/r_5d)
> - `strength.{mid,long,composite}` → 仅 09:15 全量时重算
> - `signal` → 每次刷新基于最新 short 强度 + 已缓存的 mid/long 强度做投票

**月度 Actions 用量估算**: ~1300 分钟, 安全在 2000 分钟免费额度内 (公共仓库则无限)。

### 2.2 Provider 层 — 统一数据源接口

```python
# backend/providers/base.py
class EtfDataProvider(Protocol):
    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame: ...
    def fetch_quote(self, symbol: str) -> Quote: ...

# backend/providers/yfinance_provider.py
class YfinanceProvider(EtfDataProvider):
    """美股 ETF (DRAM, SOXX, CIBR, ...)"""
    def fetch_ohlc(self, symbol, lookback_days):
        return yf.Ticker(symbol).history(period=f"{lookback_days}d")[...]

# backend/providers/akshare_provider.py
class AkshareProvider(EtfDataProvider):
    """A 股场内 ETF (512480, 512720, ...)"""
    def fetch_ohlc(self, symbol, lookback_days):
        return ak.fund_etf_hist_em(symbol=symbol, period="daily", ...)
```

**字段标准化**: 两个 provider 出来的 DataFrame 列名/时区不一致, 必须在 ETL 第一步统一:

```python
StandardOhlc = {
    'date': 'datetime64[ns, UTC]',   # 时区统一为 UTC
    'open': 'float64',
    'high': 'float64',
    'low': 'float64',
    'close': 'float64',
    'volume': 'int64',
    'amount': 'float64',              # 成交额 (亿元), A 股专用, 美股 fill NaN
}
```

### 2.3 ETL 流水线

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────────┐
│ Provider 拉 │ → │ 字段标准化   │ → │ 计算层       │ → │ JSON 写盘   │
│ raw OHLC    │   │ (时区/字段)  │   │ (返回率→评分)│   │ data/latest/│
└─────────────┘   └──────────────┘   └──────────────┘   └─────────────┘
       │
       ▼
┌─────────────┐
│ 失败 → 用 ① │  ①: 保留上次 data/latest/*.json 不动 + 写 meta.json 失败标记
└─────────────┘
```

**关键: 交易日历**
- A 股节假日跳过: 使用 `chinese_calendar` 库判断
- 美股节假日跳过: 使用 `pandas_market_calendars` 的 NYSE 日历
- 节假日 GitHub Action 仍触发, 但 pipeline 第一步检查日历即 early return

### 2.4 L1 软容灾的具体行为

| 失败场景 | 行为 | meta.json 状态 | UI 显示 |
|---------|------|---------------|---------|
| 单只 ETF 失败 | 该 ETF 字段为 null, 其他正常 | `degraded` | 该行显示「—」+ 灰色 |
| Provider 整体失败 (如 Yahoo 限流) | 不覆盖 latest/, 保留上次成功 | `stale` | 顶部黄色横幅「数据已过期 XX 分钟」 |
| GitHub Action 本身崩溃 | latest/ 不动, meta 不更新 | UI 自检: `now - meta.timestamp > 2h` | 顶部红色横幅「数据获取异常」 |

---

## 3. 算法层

### 3.1 数据预备: 标准化收益率

```python
# 给定一只 ETF 的 OHLC, 算出 6 个周期的对数收益率
returns = {
    'r_1d':   log(close_t / close_{t-1}),
    'r_5d':   log(close_t / close_{t-5}),
    'r_20d':  log(close_t / close_{t-20}),
    'r_60d':  log(close_t / close_{t-60}),
    'r_120d': log(close_t / close_{t-120}),
    'r_ytd':  log(close_t / close_{年初首交易日}),
}
```

**用对数收益率** (不是简单收益率): 跨周期可加性更好, 长周期数据更稳定, 对极端涨幅不失真。

### 3.2 强度评分 (D 双轨)

#### 3.2.1 单周期强度

```python
# 三个维度的输入收益率 (取该维度内子周期平均)
dim_returns = {
    'short': mean([r_1d, r_5d]),
    'mid':   mean([r_20d, r_60d]),
    'long':  mean([r_120d, r_ytd]),
}

# 双轨打分
def strength_per_dim(dim_return_for_etf, all_dim_returns_in_pool):
    # 轨 1: 池内百分位 (0-100), 14 主题样本
    P = percentile_rank(dim_return_for_etf, all_dim_returns_in_pool)

    # 轨 2: sigmoid 动量映射 (0-100)
    annualized = dim_return_for_etf * (252 / DAYS_IN_DIM)
    M = 100 / (1 + exp(-K_SIGMOID * (annualized - THRESHOLD)))

    return 0.5 * P + 0.5 * M
```

**参数 (写在 `config/algo.yml`, 可调)**:

| 参数 | 默认值 | 含义 |
|------|-------|------|
| `K_SIGMOID` | `5.0` | 陡度 (越大越接近阶跃) |
| `THRESHOLD` | `0.0` | sigmoid 拐点 (年化 = 0 时 M = 50) |
| `DAYS_IN_DIM[short]` | `3` | 短期等效天数 (用于年化) |
| `DAYS_IN_DIM[mid]` | `40` | 中期等效天数 |
| `DAYS_IN_DIM[long]` | `180` | 长期等效天数 |

**已验证可复现文档样本**: DRAM 中期 99 ← 年化 ≈ +300% → sigmoid 饱和到 99; 存储芯片综合 94 ← `0.2×77 + 0.4×99 + 0.4×99 = 94.6`。

#### 3.2.2 综合强度

```python
composite = 0.2 * short + 0.4 * mid + 0.4 * long
```

权重由文档样本反推, 偏向中长期 (短期太敏感容易噪声)。

#### 3.2.3 sigmoid 参数校准 (避免"分布过窄"陷阱)

**风险点**: 若不做参数校准, 简单加权算法易出现"强度全员集中在中段 (如 46-64)、强弱主题无明显区分"的失败模式。本项目通过 sigmoid 饱和段 + 池内百分位双轨结构避免此问题, 但**默认参数必须经过真实数据回测校准**。

**校准目标分布** (用 2025 全年 14 主题历史回测验证):

| 主题强弱区间 | 综合强度范围 | 占比目标 |
|------------|------------|---------|
| 真正领涨 (top 20%)  | 75-99 | 强势饱和段, sigmoid 拉满 |
| 普通中性 (mid 60%)  | 30-70 | 大多数主题落在此区间 |
| 真正落后 (bot 20%)  | 0-30  | 弱势段 |

**校准脚本**: `scripts/calibrate_algo.py`
- 输入: 2025 年全年 14 主题 OHLC 数据 (通过 bootstrap_data.py 拉取)
- 输出: 推荐的 `K_SIGMOID` 与 `THRESHOLD` 参数, 写入 `config/algo.yml`
- 验证: 按上表分布占比验证, 偏差 >15% 则报警

**若校准失败 (无论参数怎么调都满足不了)**: 退路是把综合权重从 `(0.2, 0.4, 0.4)` 调整为更倾斜中期的 `(0.15, 0.55, 0.30)`, 进一步突出中期动量主导地位。

### 3.3 映射分 (自动算 60d 相关性)

```python
def mapping_score(us_etf_returns_60d, cn_etf_returns_60d):
    # 对齐交易日 (取两市都开市的交易日 intersection)
    aligned = align_by_date(us_etf_returns_60d, cn_etf_returns_60d)
    if len(aligned) < 30:
        return None  # 数据不足

    corr = pearson_correlation(aligned.us, aligned.cn)
    # 把 [-1, 1] 映射到 [0, 100], 负相关也是有意义的"反向映射"
    return round(abs(corr) * 100)
```

**注意点**:
- 用对齐后的对数收益率算 corr (不是用价格 level)
- 美股 T-1 收盘 vs A 股 T 当日收盘 (A 股反映前夜美股的传导效应)
- 数据不足 30 个对齐日 → 返回 null, UI 显示「映射分: —」

### 3.4 置信度 (两档 hardcode)

```python
# 从 themes.yml 读 match_type
CONFIDENCE = {
    'exact': 90,   # 精确匹配 (主题对应纯 A 股 ETF)
    'wide':  60,   # 宽主题替代 (用宽行业 ETF 代替)
}
```

### 3.5 信号判定 (多周期一致性投票)

#### 3.5.1 单周期判定

```python
def judge_per_period(us_str, cn_str, us_ret, cn_ret):
    # 共振: 强度接近 + 方向一致 + 双方都不弱
    if (abs(us_str - cn_str) <= 15
        and same_sign(us_ret, cn_ret)
        and max(us_str, cn_str) >= 60):
        return 'resonance'

    # 传导: 强度落差大 (美股先行)
    if (us_str - cn_str >= 25 and us_str >= 65):
        return 'transmission'  # 美股强, A 股弱 → 等待补涨/补跌
    if (cn_str - us_str >= 25 and cn_str >= 65):
        return 'transmission'  # 反向, 罕见但保留

    # 背离: 方向相反, 双方幅度都不可忽略
    if (opposite_sign(us_ret, cn_ret)
        and abs(us_ret) >= 0.02
        and abs(cn_ret) >= 0.02):
        return 'divergence'

    return None  # 中性
```

#### 3.5.2 多周期投票

```python
def signal_for_pair(us_theme, cn_etf):
    votes = []
    for dim in ['short', 'mid', 'long']:
        votes.append(judge_per_period(
            us_str=us_theme.strength[dim],
            cn_str=cn_etf.strength[dim],
            us_ret=us_theme.dim_returns[dim],
            cn_ret=cn_etf.dim_returns[dim],
        ))

    counter = Counter(v for v in votes if v is not None)
    if counter and counter.most_common(1)[0][1] >= 2:
        return counter.most_common(1)[0][0]
    return None
```

#### 3.5.3 主题级信号聚合

一个美股主题可能对应多只 A 股 ETF (如「存储芯片」→ 512480 + 512760)。主题级显示哪个信号？

```python
def signal_for_theme(us_theme, cn_candidates):
    # 按 (confidence, mapping_score) 降序排, 取第一个 non-null 信号
    sorted_candidates = sorted(
        cn_candidates,
        key=lambda x: (x.confidence, x.mapping_score),
        reverse=True,
    )
    for cn in sorted_candidates:
        sig = signal_for_pair(us_theme, cn)
        if sig:
            return sig, cn  # 同时返回触发该信号的代表 ETF
    return None, None
```

### 3.6 算法层超参数总览 (`config/algo.yml`)

```yaml
strength:
  k_sigmoid: 5.0
  threshold: 0.0
  days_in_dim:
    short: 3
    mid: 40
    long: 180
  composite_weights:
    short: 0.2
    mid: 0.4
    long: 0.4

mapping:
  corr_window_days: 60
  min_aligned_days: 30

confidence:
  exact: 90
  wide: 60

signal:
  resonance:
    max_strength_diff: 15
    min_max_strength: 60
  transmission:
    min_strength_diff: 25
    min_leader_strength: 65
  divergence:
    min_return_magnitude: 0.02
```

所有阈值全部外置在 yml, 调参不需要改代码。

### 3.7 主题映射字典 (`config/themes.yml` 示例)

> 主题总数: **14 个** (原文档 13 个 + 新增航天军工 1 个)

```yaml
themes:
  - id: storage_dram
    name: 存储芯片
    us_etfs: [DRAM, SOXX, SMH]
    primary_us: DRAM
    tags: [DRAM, NAND, 半导体]
    note: "A股无纯存储基金, 用半导体宽主题替代"
    cn_etfs:
      - { code: '512480', name: 半导体ETF国联安, tracking: 中证全指半导体, match_type: wide }
      - { code: '512760', name: 芯片ETF,        tracking: 中华半导体芯片, match_type: wide }

  - id: cybersecurity
    name: 网络安全
    us_etfs: [CIBR, BUG]
    primary_us: CIBR
    tags: [网络安全, 计算机]
    note: "A股无纯网络安全 ETF, 映射纯度低"
    cn_etfs:
      - { code: '512720', name: 计算机ETF国泰, tracking: 中证计算机, match_type: wide }

  - id: aerospace_defense
    name: 航天军工
    us_etfs: [ITA, UFO, ARKX]
    primary_us: ITA
    tags: [航天, 军工, 国防]
    note: "A股军工 ETF 标的较精确, 置信度高"
    cn_etfs:
      - { code: '512660', name: 军工ETF,       tracking: 中证军工,     match_type: exact }
      - { code: '512710', name: 军工龙头ETF,   tracking: 中证军工龙头, match_type: exact }

  # 半导体、AI算力、原油/能源、新能源车/锂电、机器人、黄金/有色、
  # 中概互联网/港股、金融/券商银行、光伏/清洁能源、生物科技/创新药
  # 共 14 条
```

---

## 4. 数据模型 (JSON Schema)

### 4.1 设计原则

1. 前后端只通过 JSON 通信 — 后端写 JSON, 前端 fetch JSON, 零私有协议
2. schema 自描述 — 每个文件带 `schema_version`, 便于未来升级
3. `latest/` 与 `snapshots/<date>/` schema 完全相同 — 前端代码可复用
4. 冗余优于跨文件 join — signals.json 包含 `summary` 段, 前端直接显示 KPI 卡片, 不用 join 计算

### 4.2 `themes.json`

```jsonc
{
  "schema_version": "1.0",
  "generated_at": "2026-06-05T06:30:00+08:00",
  "themes": [
    {
      "id": "storage_dram",
      "name": "存储芯片",
      "us_etfs": ["DRAM", "SOXX", "SMH"],
      "primary_us": "DRAM",
      "tags": ["DRAM", "NAND", "半导体"],
      "note": "A股无纯存储基金, 用半导体宽主题替代",
      "returns": {
        "r_1d": 0.002, "r_5d": 0.148, "r_20d": 0.506,
        "r_60d": 0.823, "r_120d": 1.234, "r_ytd": 1.511
      },
      "strength": { "short": 77, "mid": 99, "long": 99, "composite": 94 },
      "rank":     { "short": 1,  "mid": 1,  "long": 1,  "composite": 1 }
    }
    // 共 14 条 (含航天军工)
  ]
}
```

### 4.3 `etfs.json`

```jsonc
{
  "schema_version": "1.0",
  "generated_at": "2026-06-05T09:15:00+08:00",
  "etfs": [
    {
      "code": "512480",
      "name": "半导体ETF国联安",
      "tracking_index": "中证全指半导体",
      "returns": {
        "r_1d": -0.007, "r_5d": -0.029, "r_20d": -0.093,
        "r_60d": -0.016, "r_120d": 0.015
      },
      "amount_yi": 0.6,                           // 当日成交额 (亿元)
      "price": 1.234,                             // 最新价
      "strength": { "short": 35, "mid": 28, "long": 42, "composite": 33 }
    }
    // 共 20 条
  ]
}
```

### 4.4 `signals.json`

```jsonc
{
  "schema_version": "1.0",
  "generated_at": "2026-06-05T09:15:00+08:00",

  // 全局汇总, 直接喂给顶部 KPI 卡片
  "summary": {
    "themes_total": 14,
    "etfs_total": 20,
    "resonance_count": 6,
    "transmission_count": 3,
    "divergence_count": 4,
    "top_theme": {
      "id": "storage_dram",
      "name": "存储芯片",
      "primary_us": "DRAM",
      "composite_strength": 94
    }
  },

  // 主题级信号 (UI 左侧"美股主题强弱榜"的"信号"列, 共 14 条)
  "theme_signals": [
    {
      "theme_id": "storage_dram",
      "signal": "resonance",                      // resonance|transmission|divergence|null
      "trigger_cn_etf": "512480",                 // 触发该信号的代表 A 股 ETF
      "votes": {
        "short": "resonance",
        "mid":   "resonance",
        "long":  null
      },
      "description": "美股领先, A股尚未完全跟随"   // 后端模板生成
    }
  ],

  // 配对级信号 (UI 底部"A股ETF候选池"的"状态"列, 以及右侧详情)
  "pair_signals": [
    {
      "theme_id": "storage_dram",
      "cn_code": "512480",
      "mapping_score": 88,                        // 自动算: 60d corr × 100
      "confidence": 60,                           // hardcode: exact=90, wide=60
      "signal": "resonance",
      "votes": { "short": "resonance", "mid": "resonance", "long": null }
    }
  ]
}
```

### 4.5 `meta.json`

```jsonc
{
  "schema_version": "1.0",
  "last_full_refresh": {
    "us": "2026-06-05T06:30:00+08:00",
    "cn": "2026-06-05T09:15:00+08:00"
  },
  "last_intraday_refresh": "2026-06-05T14:45:00+08:00",
  "providers": {
    "us": { "status": "ok", "name": "yfinance" },     // ok|degraded|stale
    "cn": { "status": "ok", "name": "akshare" }
  },
  "failed_symbols": [],
  "stale_minutes": 0,
  "calendar": {
    "us_trading_today":  true,
    "cn_trading_today":  true,
    "us_session_active": false,                       // 当前是否美股盘中
    "cn_session_active": true
  }
}
```

### 4.6 体积估算

| 文件 | 字段量 | 估算大小 |
|------|-------|---------|
| themes.json | 14 主题 × ~30 字段 | ~6 KB |
| etfs.json | 20 ETF × ~20 字段 | ~5 KB |
| signals.json | summary + 14 主题 + ~85 配对 | ~9 KB |
| meta.json | 固定 ~15 字段 | ~1 KB |
| 合计 / 天 | | ~21 KB |

**前端加载策略**: 4 个 JSON 文件**全部并行 fetch** (HTTP/2 多路复用下耗时 ≈ 单个文件耗时, 比串联"先拉 index → 再拉子文件"更快, 也更简单)。

### 4.7 Schema 演进

- 增字段: 直接加, 旧前端忽略 → 兼容
- 改字段语义: bump `schema_version` → 1.1
- 删字段: bump major → 2.0, 前端兼容窗口 1 个版本

---

## 5. 前端架构

### 5.1 SPA 形态

单页应用, 无路由。所有交互 (筛选/选中/搜索) 都在一个页面内, URL 仅可能附 `?theme=storage_dram` 用于分享。无需 react-router, 用 URL Hash 即可 (`/?theme=storage_dram&dim=mid`)。

### 5.2 组件树 (按文档 UI 1:1 映射)

```
<App>
├─ <DataProvider>                  // Context: themes/etfs/signals/meta
│   └─ <UIStateProvider>           // Context: 选中态/筛选/搜索
│       ├─ <Header>
│       │   ├─ <Logo />
│       │   ├─ <UpdateBadge />     // "更新 06-05 09:15 · 盘中刷新中" (来自 meta)
│       │   ├─ <RadarTabs />       // 跨市雷达 (当前) | 主题轮动 (v2 预留) | 持仓监控 (v3 预留)
│       │   ├─ <KpiCards />        // 顶部 7 个 KPI (来自 signals.summary)
│       │   └─ <StaleBanner />     // 数据过期告警 (来自 meta, 仅 stale/error 时显示)
│       │
│       ├─ <FilterBar>
│       │   ├─ <DimensionTabs />   // 短期/中期/长期/综合 单选
│       │   ├─ <SignalTabs />      // 全部/共振/传导/背离 单选
│       │   ├─ <SearchInput />     // 模糊搜索
│       │   └─ <Legend />          // 颜色图例
│       │
│       ├─ <MainArea>              // 左右双面板 grid
│       │   ├─ <ThemeList>         // 左侧美股主题强弱榜
│       │   │   └─ <ThemeRow />×13
│       │   └─ <ThemeDetail>       // 右侧详情面板
│       │       ├─ <ThemeHeader />     // 名称 + 描述 + 信号标签 + 操作
│       │       ├─ <MappingPanel />    // 美股映射 + 置信度
│       │       ├─ <PeriodReturns />   // 6 周期涨跌
│       │       ├─ <StrengthBars />    // 4 维强度评分
│       │       ├─ <StrengthRing />    // Recharts 环形强度图
│       │       ├─ <SignalNote />      // 信号说明文字
│       │       ├─ <TagPills />        // 关键词药丸
│       │       ├─ <Note />            // 备注灰块
│       │       └─ <RelatedEtfsMini /> // 相关 A 股 ETF 简表
│       │
│       └─ <Footer>
│           └─ <CnEtfTable>            // 底部 A 股 ETF 候选池
│               └─ <EtfRow />×20
```

### 5.3 状态管理

#### 5.3.1 远程数据 (DataProvider)

```tsx
type RemoteData = {
  themes: ThemesFile | null;
  etfs: EtfsFile | null;
  signals: SignalsFile | null;
  meta: MetaFile | null;
  isLoading: boolean;
  error: Error | null;
};

// 用 SWR + fetch 自动重拉, 5 分钟 revalidate
// 重要: 路径必须用 import.meta.env.BASE_URL 兼容 GitHub Pages 子路径 (/etf-radar/)
const D = import.meta.env.BASE_URL;  // '/etf-radar/' on Pages, '/' on local dev
const useThemes  = () => useSWR(`${D}data/latest/themes.json`,  fetcher, { refreshInterval: 300_000 });
const useEtfs    = () => useSWR(`${D}data/latest/etfs.json`,    fetcher, { refreshInterval: 300_000 });
const useSignals = () => useSWR(`${D}data/latest/signals.json`, fetcher, { refreshInterval: 300_000 });
const useMeta    = () => useSWR(`${D}data/latest/meta.json`,    fetcher, { refreshInterval: 60_000 });
```

#### 5.3.2 UI 状态 (UIStateProvider)

```tsx
type UIState = {
  selectedThemeId: string | null;     // 当前选中主题, 联动右侧+底部
  dimension: 'short' | 'mid' | 'long' | 'composite';  // 默认 'short'
  signalFilter: 'all' | 'resonance' | 'transmission' | 'divergence';  // 默认 'all'
  searchQuery: string;
};

// URL Hash 同步:  /?theme=storage_dram&dim=mid
// 用 useEffect 双向同步, 支持分享 URL
```

不引入 zustand/redux — Context + useReducer 完全够用, 组件层级浅。

### 5.4 UI 还原 — shadcn/ui 组件映射

| 文档要求 | shadcn/ui 组件 | 备注 |
|---------|---------------|------|
| KPI 卡片 | `<Card>` + `<Badge>` | 7 个并排 |
| 时间维度/信号 Tabs | `<Tabs>` | 单选切换 |
| 搜索框 | `<Input>` + lucide `Search` 图标 | 模糊搜索 |
| 主题强弱榜 | `<Table>` | 含进度条单元格 |
| 强度进度条 | `<Progress>` 或自定义 div | 蓝色填充 |
| 涨跌颜色 | `<span class="text-blue-600">` / `text-red-600` | Tailwind |
| 信号标签 | `<Badge variant="default/secondary/destructive">` | 蓝/橙区分 |
| 主题详情 | `<Card>` + 内部 grid | |
| 标签药丸 | `<Badge variant="outline">` 可点击 | |
| 环形强度图 | `<RadialBarChart>` (Recharts) | |
| ETF 表 | `<Table>` 多列 | 含成交额格式化 |
| 数据过期告警 | `<Alert variant="warning/destructive">` | 顶部横幅 |
| 问号 tooltip (REQ-018) | `<Tooltip>` + lucide `HelpCircle` | hover/click 显示, 字段定义来自 `src/lib/field-dictionary.ts` |

### 5.5 关键交互逻辑 (伪代码)

```typescript
// 1. 选中主题 → 联动右侧详情 + 底部 ETF 池
function onThemeRowClick(themeId: string) {
  setSelectedThemeId(themeId);
  // URL hash 同步: ?theme=storage_dram
}

// 2. 切换时间维度 → 重新排序主题列表
const sortedThemes = useMemo(
  () => [...themes].sort((a, b) => b.strength[dim] - a.strength[dim]),
  [themes, dim]
);

// 3. 信号筛选 + 搜索
const filteredThemes = sortedThemes.filter(t => {
  if (signalFilter !== 'all' && t.signal !== signalFilter) return false;
  if (searchQuery && !matchTheme(t, searchQuery)) return false;
  return true;
});

// 4. 底部 ETF 池 = 当前选中主题的 cn_etfs
const cnEtfs = signals.pair_signals
  .filter(p => p.theme_id === selectedThemeId)
  .map(p => ({ ...etfs.find(e => e.code === p.cn_code), ...p }));
```

### 5.6 GitHub Pages 部署配置

```typescript
// vite.config.ts
export default defineConfig({
  base: '/etf-radar/',        // 仓库名作为子路径
  plugins: [react()],
  build: { outDir: 'dist' },
  publicDir: '../data',       // 数据目录, 构建时复制到 dist/data/
});
```

```yaml
# .github/workflows/deploy-frontend.yml
on:
  push:
    branches: [main]
    paths: ['frontend/**', 'data/**']  # 数据变化也触发部署
jobs:
  deploy:
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npm ci && npm run build
      - uses: peaceiris/actions-gh-pages@v3
        with:
          publish_dir: ./frontend/dist
```

### 5.7 性能预算

| 指标 | 预算 | 实际估算 |
|-----|------|---------|
| Bundle (gzip) | ≤ 100 KB | ~70 KB (React + shadcn + Recharts) |
| 数据载荷 (首次) | ≤ 50 KB | ~20 KB (4 个 JSON) |
| 首屏 LCP | ≤ 3 s | ~1.5 s (静态资源 + CDN) |
| 筛选切换 | ≤ 500 ms | <50 ms (纯前端 filter) |

满足 NFR-001。

---

## 6. 收尾

### 6.1 完整目录树

```
etf-radar/
├── .github/
│   └── workflows/
│       ├── us-refresh.yml          # cron: 30 22 * * 1-5 (北京 06:30)
│       ├── cn-refresh.yml          # cron: 15 1 + */15 1-7 * * 1-5
│       ├── cn-eod-archive.yml      # cron: 30 7 * * 1-5  (北京 15:30)
│       └── deploy-frontend.yml     # on: push: paths
│
├── backend/                        # Python 数据流水线
│   ├── pyproject.toml
│   ├── src/
│   │   ├── providers/
│   │   │   ├── base.py             # EtfDataProvider Protocol
│   │   │   ├── yfinance_provider.py
│   │   │   └── akshare_provider.py
│   │   ├── scoring/
│   │   │   ├── strength.py
│   │   │   ├── mapping.py
│   │   │   └── signals.py
│   │   ├── etl/
│   │   │   ├── standardize.py
│   │   │   └── calendar.py
│   │   ├── output/
│   │   │   ├── writer.py
│   │   │   └── archiver.py
│   │   ├── config_loader.py
│   │   └── pipeline.py             # 主入口 (支持 --mode={full,intraday,archive})
│   └── tests/
│       ├── unit/
│       ├── fixtures/sample_ohlc.csv
│       └── integration/test_pipeline_e2e.py
│
├── frontend/                       # React SPA
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── types/
│       ├── providers/
│       ├── hooks/
│       ├── components/
│       ├── lib/
│       │   ├── format.ts
│       │   ├── filters.ts
│       │   └── field-dictionary.ts # 字段定义 (问号 tooltip REQ-018)
│       └── tests/
│
├── config/
│   ├── themes.yml                  # 14 主题映射字典 (含航天军工)
│   └── algo.yml                    # 算法超参数
│
├── data/
│   ├── latest/{themes,etfs,signals,meta}.json
│   └── snapshots/<YYYY-MM-DD>/{themes,etfs,signals,meta}.json
│
├── docs/
│   ├── htsc-us-cn-linkage-product-doc.md
│   ├── htsc-us-cn-linkage-requirements.md
│   └── superpowers/specs/2026-06-05-etf-radar-design.md
│
├── scripts/
│   ├── bootstrap_data.py            # 首次种子, 拉 1 年历史回填
│   ├── calibrate_algo.py            # sigmoid 参数校准 (用历史数据回测)
│   └── archive_cleanup.py           # 删除 >2 年的 snapshots
│
├── README.md
└── .gitignore
```

### 6.2 错误处理边界

| 层 | 错误类型 | 处理策略 | 用户感知 |
|----|---------|---------|---------|
| Provider | API 超时 | retry 3 次 + 指数退避, 最后失败抛 `ProviderError` | UI 顶部黄色横幅 |
| Provider | 返回空数据 | 抛 `EmptyDataError`, 不写盘 | 同上 |
| ETL | 单只 ETF 字段缺失 | `warn` + 该 ETF 字段填 null | 表格里显示「—」 |
| ETL | 时区/类型异常 | 中断, 抛 `SchemaError`, 不写盘 | UI 顶部红色横幅 |
| Scoring | 数据不足 30 天 | 该指标返回 null, 其他正常计算 | 字段显示「—」 |
| Output | JSON 写入失败 | 中断, 保留 `latest/` 上次成功 | 数据过期告警 |
| Pipeline | 整体崩溃 | catch all + 写 `meta.json` 失败状态 | UI 自检 → 红色告警 |
| Frontend | fetch JSON 失败 | 重试 1 次 + `<ErrorBoundary>` 兜底 | 友好错误页 + 重试按钮 |
| Frontend | 字段缺失/类型错 | 静默降级显示 "—" | 局部缺失 |

**核心原则**:
1. 后端: 宁可不写, 不要写错 (保留 latest 上次成功比写错数据更安全)
2. 前端: 宁可降级, 不要崩溃 (局部缺失用 "—", 避免整页白屏)
3. meta.json 是单一真相 (所有健康信号都汇总在这里)

### 6.3 测试策略

#### 后端

| 类型 | 工具 | 覆盖 |
|------|------|------|
| 单元测试 | pytest | strength (8+ 用例)、mapping (5+)、signals (10+, 含投票边界) |
| 集成测试 | pytest + fixture CSV | 全 pipeline, 输入历史 OHLC → 输出符合 schema 的 JSON |
| Schema 校验 | jsonschema | 输出 JSON 必须通过 schema 校验 (CI 强制) |
| Provider 测试 | pytest + responses mock | mock yfinance/akshare HTTP, 验证字段标准化 |

#### 前端

| 类型 | 工具 | 覆盖 |
|------|------|------|
| 组件测试 | Vitest + Testing Library | KpiCards、ThemeRow 渲染; 交互如选中/筛选 |
| Hook 测试 | Vitest | useFilteredThemes 边界 (空数据/不匹配) |
| 视觉回归 | (可选) Playwright | 关键页面截图 diff |

最小必要: 只测纯函数 (lib/filters.ts、lib/format.ts) 和关键 hook, shadcn/ui 组件本身不测。

#### CI 流程

```yaml
# .github/workflows/ci.yml (test 触发)
on: [push, pull_request]
jobs:
  backend:      pytest backend/tests
  frontend:     cd frontend && npm test && npm run build
  schema-check: validate data/latest/*.json against schemas/
```

### 6.4 监控与可观测性

| 监控点 | 实现 | 告警渠道 |
|-------|------|---------|
| 数据时效 | `meta.json` → 前端横幅 | UI 提示用户 |
| GitHub Action 失败 | Actions 内置邮件 | GitHub 自动发给 owner |
| Provider 失败趋势 | `failed_symbols` 列表纳入 `meta.json` | UI 详情可展开查看 |
| 数据 schema 偏移 | CI 强制 schema 校验 | PR / push 阶段拦截 |

**显式放弃的监控**: Sentry 错误上报 (个人静态网页过度)、日志聚合 (用 Actions 自带 logs 足够)。

---

## 附录 A — 决策摘要

| # | 主题 | 最终决策 |
|---|------|---------|
| Q1 | 交付形态 | GitHub Action 定时跑 + 静态网页 (GitHub Pages) + 无登录 |
| Q2 | 调度节奏 | 美股 1次/日 (06:30) + A股盘前 1次 (09:15) + 交易时段 15min 刷价 |
| Q3 | 数据源 | yfinance + AkShare + L1 软容灾 (失败保留快照 + UI 告警) |
| Q4 | 强度算法 | 双轨 (百分位 50% + sigmoid 动量 50%) |
| Q5 | 主题映射 | 混合 (hardcode 主题↔ETF + 自动算 corr 映射分 + 两档置信度) |
| Q6 | 信号判定 | 多周期一致性投票 (短/中/长 3 周期 ≥ 2 同标签才生效) |
| Q7 | 前端栈 | React + Vite + TS + TailwindCSS + shadcn/ui + Recharts |
| Q8 | 数据布局 | `latest/` 实时 + `snapshots/YYYY-MM-DD/` 按日期分目录 (不合并文件) |
| Q9 | 项目结构 | 单仓 Monorepo |

---

## 附录 B — 显式不做的事 (YAGNI)

| 不做 | 原因 |
|------|------|
| 用户系统 / 登录 | 无登录是产品决策 |
| 数据库 / Redis | git 即数据库 |
| WebSocket 实时推送 | 15 min 刷新已够 |
| 移动端原生 App | 静态 Web 桌面优先 |
| 国际化 i18n | 仅中文用户 |
| 暗黑模式 | 后续可加, 初版省 |
| 历史回测可视化 | snapshots 已存, UI 后续迭代 |
| 通知推送 (邮件/微信) | 工具型产品, 用户主动看 |
| 数据源主备切换 | L1 软容灾已覆盖 95% 场景 |
| Sentry 前端错误上报 | 个人静态网页过度 |
| 实时 tick 行情 | 定位为延迟数据快照型工具 |

---

## 附录 C — 与原需求文档的偏差说明

| 原需求 | 偏差 | 说明 |
|-------|------|------|
| REQ-016「使用实时/延迟行情数据」 | **修正为延迟报价 (~15 分钟)** | yfinance/AkShare 实际是延迟数据, UI 上明确标注「数据延迟」避免误解 |
| REQ-015「盘中时段自动定时刷新 (频率待定)」 | **明确为 15 分钟** | 由 GitHub Action cron 强制 |
| REQ-013「背离信号说明文字 (具体文案待定)」 | **补全为「美股 A 股走势不同步, 需二次确认」** | 在 themes.yml 模板中固化 |
| 数据来源「具体频率待确认」 | **见 2.1 调度表** | |
| 评分体系「公式未给出」 | **见 3.2-3.5 节** | 所有公式 + 阈值已固化到 algo.yml |

---

## 附录 D — 未来路线图

UI 中的 `<RadarTabs />` 预留了多雷达扩展空间。当前 v1 只实现「跨市雷达」, 后续版本路线图:

| 版本 | Tab | 价值主张 | 数据来源 |
|------|-----|---------|---------|
| **v1 (本设计)** | 跨市雷达 | 美股主题 → A 股 ETF 联动信号 | yfinance + AkShare |
| v2 候选 | 主题轮动 | 板块强弱在时间轴上的迁移热力图 | 复用 v1 数据 + 时间序列展开 |
| v3 候选 | 持仓监控 | ETF 实际持仓变化 (北上资金流、ETF 份额变动) | AkShare 拓展接口 |
| v∞ | 由用户反馈决定 | | |

**架构原则**: 新雷达只需添加新的 workflow + 新的 JSON 文件 + 新的 React 组件树, 现有「跨市雷达」零修改。

---

## 文档状态

- ✅ 1.0 (2026-06-05): 头脑风暴产出, 初版
- ✅ 1.1 (2026-06-05): 主题扩容至 14 (含航天军工), 增补 sigmoid 校准方法, 组件树增加 RadarTabs/UpdateBadge, 字段字典实化问号 tooltip
- ✅ 1.2 (2026-06-05): YAGNI 修剪 — 4 个 JSON 文件统一并行 fetch (HTTP/2 多路复用), 不引入聚合入口文件
- ⏳ 待: 用户审阅 → 进入 writing-plans 阶段 → 拆分实施 plan
