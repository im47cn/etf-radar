# 主题成分股 Phase 2 — 个股技术指标实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为主题成分股页面新增 4 个核心技术指标（60d/20d 强度、RSI、量比）+ 龙头自动标注 + 60 日 K 线 hover 小图 + 主题结构诊断摘要。

**Architecture:** Backend 走「一次性 backfill workflow_dispatch + 工作日盘后 daily cron 增量」双管道；强度计算用 scipy.stats.rankdata 向量化避免 5000² 复杂度；RSI 用 `ta` 库；前端新增 SVG 原生 K 线小图、徽章组件与结构诊断模块，StockTable 默认按 `leader desc → strength_60d desc` 排序。

**Tech Stack:** Python 3.11 / Pydantic v2 / akshare / scipy / pandas / ta / pytest / React 18 + TypeScript / Vitest

**关联 Spec:** [2026-06-25-theme-stocks-phase-2-design.md](../specs/2026-06-25-theme-stocks-phase-2-design.md)

---

## 文件总览

**Backend 新建：**
- `backend/src/scoring/stock_indicators.py` — RSI(14) + 量比
- `backend/src/scoring/leader_rule.py` — 龙头标签规则
- `backend/src/providers/stock_history_provider.py` — akshare 历史 K 线
- `backend/src/stocks_history_pipeline.py` — 一次性 backfill CLI
- `backend/src/stocks_daily_pipeline.py` — 工作日盘后 daily CLI
- `backend/tests/test_strength_batch_equivalence.py`
- `backend/tests/test_stock_indicators.py`
- `backend/tests/test_leader_rule.py`
- `backend/tests/test_stock_history_provider.py`
- `backend/tests/test_stocks_history_pipeline.py`
- `backend/tests/test_stocks_daily_pipeline.py`

**Backend 修改：**
- `backend/src/models.py` — 加 StockIndicators / StockOhlcBar / StockOhlc
- `backend/src/scoring/strength.py` — 加 batch_strength_per_dim
- `backend/tests/test_output_schemas.py` — 加 4 个 schema round-trip
- `backend/pyproject.toml` — 加 ta 依赖

**Frontend 新建：**
- `frontend/src/types/stockIndicators.ts`
- `frontend/src/lib/holdings/useStockIndicators.ts`
- `frontend/src/lib/holdings/useStockOhlc.ts`
- `frontend/src/lib/stocks/indicatorThresholds.ts`
- `frontend/src/lib/stocks/structureInsight.ts`
- `frontend/src/lib/stocks/leaderRank.ts`
- `frontend/src/components/stocks/StrengthBadge.tsx`
- `frontend/src/components/stocks/RSIBadge.tsx`
- `frontend/src/components/stocks/VolumeRatioBadge.tsx`
- `frontend/src/components/stocks/MiniKlineChart.tsx`
- `frontend/src/components/stocks/ThemeStructureSummary.tsx`
- `frontend/src/lib/holdings/__tests__/useStockIndicators.test.ts`
- `frontend/src/lib/holdings/__tests__/useStockOhlc.test.ts`
- `frontend/src/lib/stocks/__tests__/structureInsight.test.ts`
- `frontend/src/lib/stocks/__tests__/leaderRank.test.ts`
- `frontend/src/components/stocks/__tests__/MiniKlineChart.test.tsx`
- `frontend/src/components/stocks/__tests__/ThemeStructureSummary.test.tsx`

**Frontend 修改：**
- `frontend/src/types/holdings.ts` — AggregatedStock 加 indicators 可选字段
- `frontend/src/lib/dataUrls.ts` — 加 STOCKS_URLS + stockOhlcUrl
- `frontend/src/lib/holdings/aggregator.ts` — 接受 indicators 参数 join
- `frontend/src/components/stocks/StockTable.tsx` — 加 4 列 + 排序 + hover
- `frontend/src/pages/StocksPage.tsx` — 接入 ThemeStructureSummary + indicators hook
- `frontend/src/components/stocks/__tests__/StockTable.test.tsx`（若不存在则新增）

**CI 新建：**
- `.github/workflows/stocks-history-backfill.yml`
- `.github/workflows/stocks-daily.yml`

**CI 修改：**
- `.github/workflows/deploy-frontend.yml` — paths 排除 backend-only 文件

---

## Task 1: Backend models 扩展 + schema 契约

**Files:**
- Modify: `backend/src/models.py` (in 191-196 之后追加)
- Modify: `backend/tests/test_output_schemas.py`

- [ ] **Step 1: 写失败的 schema round-trip 测试**

在 `backend/tests/test_output_schemas.py` 末尾追加：

```python
def test_stock_indicators_roundtrip():
    from src.models import StockIndicators
    payload = {
        'name': 'TCL中环', 'strength_60d': 87, 'strength_20d': 91,
        'rsi_14': 62.3, 'vol_ratio': 1.85, 'leader': '⭐⭐',
    }
    obj = StockIndicators.model_validate(payload)
    assert obj.model_dump() == payload


def test_stock_indicators_null_fields():
    from src.models import StockIndicators
    payload = {
        'name': '退市股', 'strength_60d': None, 'strength_20d': None,
        'rsi_14': None, 'vol_ratio': None, 'leader': '',
    }
    obj = StockIndicators.model_validate(payload)
    assert obj.strength_60d is None
    assert obj.leader == ''


def test_stock_ohlc_roundtrip():
    from datetime import date, datetime, timezone
    from src.models import StockOhlc, StockOhlcBar
    obj = StockOhlc(
        code='002129', name='TCL中环',
        generated_at=datetime(2026, 6, 25, 8, 30, tzinfo=timezone.utc),
        bars=[StockOhlcBar(date=date(2026, 4, 1), o=12.3, h=12.65, l=12.2, c=12.5, v=5230000)],
    )
    dumped = obj.model_dump(mode='json')
    StockOhlc.model_validate(dumped)
    assert dumped['bars'][0]['v'] == 5230000


def test_stock_ohlc_bars_max_60():
    """bars 列表长度允许 0-60 任意值（spec 约定 ≤ 60 但停牌日跳过可少于）"""
    from src.models import StockOhlc
    StockOhlc.model_validate({
        'code': '999999', 'name': '空', 'generated_at': '2026-06-25T00:00:00+00:00',
        'bars': [],
    })
```

- [ ] **Step 2: 跑测试，期望 ImportError**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_output_schemas.py -k "stock_indicators or stock_ohlc" -v 2>&1 | tail -10
```
Expected: 4 FAILED with `ImportError: cannot import name 'StockIndicators'`

- [ ] **Step 3: 在 models.py 加新模型**

在 `backend/src/models.py` 末尾（第 196 行后）追加：

```python


class StockIndicators(BaseModel):
    """主题成分股每日指标聚合（写入 data/stocks/holdings_indicators.json::stocks[code]）。

    所有数值字段在数据不足 / 停牌时设为 None；前端统一显示「—」。
    leader 字段为非空字符串时表示龙头标签。
    """
    name: str
    strength_60d: Optional[int] = Field(default=None, ge=0, le=99)
    strength_20d: Optional[int] = Field(default=None, ge=0, le=99)
    rsi_14: Optional[float] = Field(default=None, ge=0, le=100)
    vol_ratio: Optional[float] = Field(default=None, ge=0)
    leader: str = ''  # "⭐⭐⭐" | "⭐⭐" | "⭐" | ""


class StockOhlcBar(BaseModel):
    """单日 OHLC 加成交量。"""
    date: _Date
    o: float
    h: float
    l: float
    c: float
    v: int = Field(ge=0)


class StockOhlc(BaseModel):
    """单只个股 60 日 K 线（写入 data/stocks/ohlc/{code}.json）。"""
    code: str
    name: str
    generated_at: _Datetime
    bars: list[StockOhlcBar] = Field(max_length=60)
```

- [ ] **Step 4: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_output_schemas.py -k "stock_indicators or stock_ohlc" -v 2>&1 | tail -10
```
Expected: 4 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/src/models.py backend/tests/test_output_schemas.py
git commit -m "feat(models): add StockIndicators / StockOhlc / StockOhlcBar for Phase 2"
```

---

## Task 2: strength.py 向量化批量函数

**Files:**
- Modify: `backend/src/scoring/strength.py`
- Create: `backend/tests/test_strength_batch_equivalence.py`

- [ ] **Step 1: 写等价性测试**

新建 `backend/tests/test_strength_batch_equivalence.py`：

```python
"""batch_strength_per_dim 与 strength_per_dim 逐元素等价（round 后 ±1 误差容忍）"""
import math

import numpy as np
import pytest

from src.scoring.strength import batch_strength_per_dim, strength_per_dim


def test_batch_matches_single_no_nan():
    rng = np.random.default_rng(42)
    returns = rng.uniform(-0.5, 0.5, size=1000)
    batch_out = batch_strength_per_dim(returns.copy(), k=2.0, days_in_dim=60)
    for i, r in enumerate(returns):
        single = strength_per_dim(r, returns.tolist(), k=2.0, days_in_dim=60)
        assert abs(int(batch_out[i]) - single) <= 1, f'mismatch at {i}'


def test_batch_propagates_nan():
    arr = np.array([0.1, np.nan, 0.2, np.nan, 0.3])
    out = batch_strength_per_dim(arr, k=2.0, days_in_dim=60)
    assert np.isnan(out[1])
    assert np.isnan(out[3])
    assert not np.isnan(out[0])


def test_batch_all_nan_returns_all_nan():
    arr = np.array([np.nan, np.nan, np.nan])
    out = batch_strength_per_dim(arr, k=2.0, days_in_dim=60)
    assert np.all(np.isnan(out))


def test_batch_empty_array():
    out = batch_strength_per_dim(np.array([]), k=2.0, days_in_dim=60)
    assert len(out) == 0


def test_batch_all_equal_returns_same_score():
    """所有元素相等时百分位应为 50（average rank），M 也相同 → score 相同"""
    arr = np.full(100, 0.1)
    out = batch_strength_per_dim(arr, k=2.0, days_in_dim=60)
    assert len(set(out.tolist())) == 1


def test_batch_score_range_0_to_99():
    rng = np.random.default_rng(0)
    arr = rng.uniform(-2.0, 2.0, size=500)
    out = batch_strength_per_dim(arr, k=2.0, days_in_dim=60)
    valid = out[~np.isnan(out)]
    assert valid.min() >= 0
    assert valid.max() <= 99
```

- [ ] **Step 2: 跑测试，期望 ImportError**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_strength_batch_equivalence.py -v 2>&1 | tail -15
```
Expected: 6 FAILED with `ImportError: cannot import name 'batch_strength_per_dim'`

- [ ] **Step 3: 在 strength.py 末尾加批量函数**

在 `backend/src/scoring/strength.py` 末尾追加：

```python


def batch_strength_per_dim(
    returns_array: 'np.ndarray',
    k: float,
    days_in_dim: int,
) -> 'np.ndarray':
    """向量化版本：N 只股一次性算百分位 + 动量。

    避免 N² 复杂度（原 strength_per_dim 每只股都遍历 pool）。
    输入 NaN 自动传播；返回数组中无效位置保持 NaN。

    Returns:
        长度 N 的 float ndarray，有效值在 [0, 99]，无效为 NaN。
    """
    import numpy as np
    from scipy.stats import rankdata  # type: ignore[import-untyped]

    n = len(returns_array)
    if n == 0:
        return np.array([], dtype=float)

    valid_mask = ~np.isnan(returns_array)
    n_valid = int(valid_mask.sum())

    P = np.full(n, np.nan)
    if n_valid > 0:
        ranks = rankdata(returns_array[valid_mask], method='average')
        P[valid_mask] = (ranks / n_valid) * 100

    annualized = returns_array * (252 / days_in_dim)
    M = 100.0 / (1.0 + np.exp(-k * annualized))

    raw = 0.5 * P + 0.5 * M
    score = np.clip(np.round(raw), 0, 99)
    score[np.isnan(raw)] = np.nan
    return score
```

- [ ] **Step 4: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_strength_batch_equivalence.py -v 2>&1 | tail -15
```
Expected: 6 PASS

- [ ] **Step 5: 跑全部 backend 测试确保未影响既有**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -5
```
Expected: 所有测试 PASS（包含原有 + 新增 6 个）

- [ ] **Step 6: 提交**

```bash
git add backend/src/scoring/strength.py backend/tests/test_strength_batch_equivalence.py
git commit -m "feat(scoring): add batch_strength_per_dim vectorized for 5000 stocks"
```

---

## Task 3: scoring/stock_indicators.py — RSI + 量比

**Files:**
- Create: `backend/src/scoring/stock_indicators.py`
- Create: `backend/tests/test_stock_indicators.py`
- Modify: `backend/pyproject.toml` (加 ta 依赖)

- [ ] **Step 1: 加 ta 依赖**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv add ta
```

- [ ] **Step 2: 写失败测试**

新建 `backend/tests/test_stock_indicators.py`：

```python
"""RSI(14) 与 量比 计算"""
import math

import pytest

from src.scoring.stock_indicators import compute_rsi, compute_volume_ratio


def test_rsi_insufficient_data_returns_none():
    """少于 15 个有效收盘价 → None"""
    closes = [10.0] * 14
    assert compute_rsi(closes) is None


def test_rsi_constant_prices_returns_50_or_nan():
    """价格全相等时 ta 库的 RSI 行为：可能返回 NaN（无变化）或 50"""
    closes = [10.0] * 30
    result = compute_rsi(closes)
    assert result is None or result == 50.0


def test_rsi_strict_uptrend_near_100():
    """严格单调上涨 30 日 → RSI 应接近 100"""
    closes = [10.0 + i * 0.5 for i in range(30)]
    rsi = compute_rsi(closes)
    assert rsi is not None and rsi > 95.0


def test_rsi_strict_downtrend_near_0():
    """严格单调下跌 → RSI 应接近 0"""
    closes = [30.0 - i * 0.5 for i in range(30)]
    rsi = compute_rsi(closes)
    assert rsi is not None and rsi < 5.0


def test_rsi_skips_none_values():
    """收盘价含 None（停牌）→ dropna 后用剩余"""
    closes = [10.0 + i * 0.5 if i % 5 != 0 else None for i in range(40)]
    rsi = compute_rsi(closes)
    assert rsi is not None
    assert 0 <= rsi <= 100


def test_volume_ratio_standard():
    """今日量 / 前 5 日均量"""
    volumes = [100, 100, 100, 100, 100, 200]
    # mean(前 5) = 100, ratio = 200/100 = 2.0
    assert compute_volume_ratio(volumes) == 2.0


def test_volume_ratio_with_today_none_returns_none():
    volumes = [100, 100, 100, 100, 100, None]
    assert compute_volume_ratio(volumes) is None


def test_volume_ratio_insufficient_prev_returns_none():
    """前 5 日有效量不足 5 个"""
    volumes = [100, None, None, 100, 100, 200]
    assert compute_volume_ratio(volumes) is None


def test_volume_ratio_zero_mean_returns_none():
    """前 5 日均量为 0（极端停牌）"""
    volumes = [0, 0, 0, 0, 0, 100]
    assert compute_volume_ratio(volumes) is None


def test_volume_ratio_length_lt_6_returns_none():
    assert compute_volume_ratio([100, 200, 300]) is None
```

- [ ] **Step 3: 跑测试，期望 ModuleNotFoundError**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_stock_indicators.py -v 2>&1 | tail -15
```
Expected: collection error - `ModuleNotFoundError: No module named 'src.scoring.stock_indicators'`

- [ ] **Step 4: 实现 stock_indicators.py**

新建 `backend/src/scoring/stock_indicators.py`：

```python
"""个股技术指标计算（RSI / 量比）"""
from __future__ import annotations

import pandas as pd
from ta.momentum import RSIIndicator


def compute_rsi(closes: list[float | None], period: int = 14) -> float | None:
    """Wilder's RSI(period) 使用 ta 库实现。

    不足 period+1 个有效收盘价时返回 None；
    ta 库结果为 NaN（如全等数据）时也返回 None。
    """
    series = pd.Series([c for c in closes if c is not None], dtype=float)
    if len(series) < period + 1:
        return None
    rsi = RSIIndicator(close=series, window=period, fillna=False).rsi()
    last = rsi.iloc[-1]
    if pd.isna(last):
        return None
    return round(float(last), 1)


def compute_volume_ratio(volumes: list[int | None]) -> float | None:
    """A 股标准量比：今日量 / 前 5 个交易日均量。

    要求 volumes 长度 ≥ 6，且：
      - volumes[-1] 不为 None
      - volumes[-6:-1] 中至少 5 个为正
      - 前 5 日均量 > 0
    """
    if len(volumes) < 6:
        return None
    today = volumes[-1]
    if today is None:
        return None
    prev_5 = [v for v in volumes[-6:-1] if v is not None and v > 0]
    if len(prev_5) < 5:
        return None
    mean_prev = sum(prev_5) / 5
    if mean_prev <= 0:
        return None
    return round(today / mean_prev, 2)
```

- [ ] **Step 5: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_stock_indicators.py -v 2>&1 | tail -15
```
Expected: 10 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/src/scoring/stock_indicators.py backend/tests/test_stock_indicators.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(scoring): add stock_indicators (RSI via ta lib + volume ratio)"
```

---

## Task 4: scoring/leader_rule.py — 龙头标签规则

**Files:**
- Create: `backend/src/scoring/leader_rule.py`
- Create: `backend/tests/test_leader_rule.py`

- [ ] **Step 1: 写覆盖所有边界的测试**

新建 `backend/tests/test_leader_rule.py`：

```python
"""龙头规则边界与组合"""
from src.scoring.leader_rule import classify_leader


def test_three_star_strength_90_rsi_in_band():
    """strength >= 90 且 RSI ∈ [50, 70] → ⭐⭐⭐"""
    assert classify_leader(90, 50.0) == '⭐⭐⭐'
    assert classify_leader(95, 65.0) == '⭐⭐⭐'
    assert classify_leader(99, 70.0) == '⭐⭐⭐'


def test_strength_90_but_rsi_overbought_degrades_to_one():
    """strength 90 但 RSI > 70（超买）→ 不入 ⭐⭐⭐ / ⭐⭐，仅 ⭐"""
    assert classify_leader(90, 71.0) == '⭐'
    assert classify_leader(95, 80.0) == '⭐'


def test_two_star_strength_80_rsi_in_extended_band():
    """strength ∈ [80, 89] 且 RSI ∈ [45, 70] → ⭐⭐"""
    assert classify_leader(80, 45.0) == '⭐⭐'
    assert classify_leader(85, 60.0) == '⭐⭐'
    assert classify_leader(89, 70.0) == '⭐⭐'


def test_one_star_strength_70_plus_rsi_outside_band():
    """strength ≥ 70 但 RSI 不在范围内 → ⭐"""
    assert classify_leader(85, 40.0) == '⭐'  # RSI 低于 45
    assert classify_leader(70, 50.0) == '⭐'
    assert classify_leader(79, 75.0) == '⭐'


def test_no_label_strength_below_70():
    """strength < 70 → 空字符串"""
    assert classify_leader(69, 60.0) == ''
    assert classify_leader(50, 50.0) == ''
    assert classify_leader(0, 30.0) == ''


def test_strength_none_returns_empty():
    """strength_60d 缺失 → 空（无法判定）"""
    assert classify_leader(None, 60.0) == ''
    assert classify_leader(None, None) == ''


def test_rsi_none_falls_back_to_strength_only():
    """RSI 缺失时仅看 strength：≥ 70 给 ⭐，否则空"""
    assert classify_leader(90, None) == '⭐'
    assert classify_leader(70, None) == '⭐'
    assert classify_leader(69, None) == ''


def test_boundary_strength_exact_80_rsi_70():
    """边界值：strength=80 RSI=70 → ⭐⭐（80≥80 且 45≤70≤70）"""
    assert classify_leader(80, 70.0) == '⭐⭐'


def test_boundary_strength_exact_90_rsi_50():
    """边界值：strength=90 RSI=50 → ⭐⭐⭐"""
    assert classify_leader(90, 50.0) == '⭐⭐⭐'
```

- [ ] **Step 2: 跑测试，期望 ImportError**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_leader_rule.py -v 2>&1 | tail -15
```
Expected: 9 FAILED / collection error

- [ ] **Step 3: 实现 leader_rule.py**

新建 `backend/src/scoring/leader_rule.py`：

```python
"""龙头标签规则（仅作提示，不替代用户判断）。

设计：
- 量比作为单日噪声指标，不进入长期"龙头"判定，仅作辅助列展示
- RSI 仅作"未超买"过滤器，避免追高
- 缺失数据下退化到 strength-only 规则，避免一刀切置空
"""
from __future__ import annotations


def classify_leader(
    strength_60d: int | None,
    rsi_14: float | None,
) -> str:
    """返回龙头标签字符串。

    规则：
      strength_60d 为 None → ''
      RSI 为 None → strength ≥ 70 给 '⭐'，否则 ''
      strength ≥ 90 且 RSI ∈ [50, 70] → '⭐⭐⭐'
      strength ≥ 80 且 RSI ∈ [45, 70] → '⭐⭐'
      strength ≥ 70 → '⭐'
      其他 → ''
    """
    if strength_60d is None:
        return ''
    if rsi_14 is None:
        return '⭐' if strength_60d >= 70 else ''
    if strength_60d >= 90 and 50.0 <= rsi_14 <= 70.0:
        return '⭐⭐⭐'
    if strength_60d >= 80 and 45.0 <= rsi_14 <= 70.0:
        return '⭐⭐'
    if strength_60d >= 70:
        return '⭐'
    return ''
```

- [ ] **Step 4: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_leader_rule.py -v 2>&1 | tail -15
```
Expected: 9 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/src/scoring/leader_rule.py backend/tests/test_leader_rule.py
git commit -m "feat(scoring): add leader_rule (⭐⭐⭐ / ⭐⭐ / ⭐) based on strength + RSI"
```

---

## Task 5: providers/stock_history_provider.py

**Files:**
- Create: `backend/src/providers/stock_history_provider.py`
- Create: `backend/tests/test_stock_history_provider.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_stock_history_provider.py`：

```python
"""Provider wraps ak.stock_zh_a_hist with retry + symbol encoding"""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.providers.stock_history_provider import (
    StockHistoryFetchError,
    StockHistoryProvider,
)


def _fake_df(code: str = '002129') -> pd.DataFrame:
    return pd.DataFrame({
        '日期': pd.to_datetime(['2026-04-01', '2026-04-02']),
        '开盘': [12.3, 12.5],
        '最高': [12.65, 12.7],
        '最低': [12.2, 12.4],
        '收盘': [12.5, 12.6],
        '成交量': [5230000, 6100000],
    })


def test_fetch_history_success():
    p = StockHistoryProvider()
    with patch('akshare.stock_zh_a_hist', return_value=_fake_df()):
        bars = p.fetch_history('002129', days=60)
    assert len(bars) == 2
    assert bars[0].o == 12.3
    assert bars[0].c == 12.5
    assert bars[1].v == 6100000


def test_fetch_history_empty_df_raises():
    p = StockHistoryProvider()
    with patch('akshare.stock_zh_a_hist', return_value=pd.DataFrame()):
        with pytest.raises(StockHistoryFetchError):
            p.fetch_history('002129', days=60)


def test_fetch_history_retries_on_exception_then_succeeds():
    p = StockHistoryProvider(max_retries=2, base_backoff=0.001)
    call_count = [0]

    def flaky(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ConnectionError('network')
        return _fake_df()

    with patch('akshare.stock_zh_a_hist', side_effect=flaky):
        bars = p.fetch_history('002129', days=60)
    assert call_count[0] == 2
    assert len(bars) == 2


def test_fetch_history_exhausts_retries():
    p = StockHistoryProvider(max_retries=2, base_backoff=0.001)
    with patch('akshare.stock_zh_a_hist', side_effect=ConnectionError('down')):
        with pytest.raises(StockHistoryFetchError):
            p.fetch_history('002129', days=60)


def test_truncates_to_requested_days():
    """如果 akshare 返回超过 days 行，截取尾部 days 个"""
    df = pd.DataFrame({
        '日期': pd.to_datetime([f'2026-{m:02d}-{d:02d}' for m in [3, 4] for d in range(1, 6)]),
        '开盘': [10.0] * 10, '最高': [10.5] * 10, '最低': [9.5] * 10,
        '收盘': [10.2] * 10, '成交量': [1000] * 10,
    })
    p = StockHistoryProvider()
    with patch('akshare.stock_zh_a_hist', return_value=df):
        bars = p.fetch_history('002129', days=5)
    assert len(bars) == 5
    assert bars[0].date == date(2026, 4, 1)
```

- [ ] **Step 2: 跑测试，期望 ImportError**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_stock_history_provider.py -v 2>&1 | tail -15
```
Expected: collection error / ImportError

- [ ] **Step 3: 实现 stock_history_provider.py**

新建 `backend/src/providers/stock_history_provider.py`：

```python
"""个股历史 K 线 Provider（封装 ak.stock_zh_a_hist）"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import akshare as ak
import pandas as pd

from ..models import StockOhlcBar

log = logging.getLogger(__name__)


class StockHistoryFetchError(Exception):
    """历史 K 线抓取失败（含重试耗尽与空返回）"""


@dataclass
class StockHistoryProvider:
    """封装 akshare 历史接口 + 指数退避重试。

    akshare 对 symbol 前缀自动判断（'sh' / 'sz' / 'bj'），
    本 Provider 不做手工前缀，直接传 6 位 code。
    """
    max_retries: int = 3
    base_backoff: float = 0.5

    def fetch_history(self, code: str, days: int) -> list[StockOhlcBar]:
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                df: pd.DataFrame = ak.stock_zh_a_hist(
                    symbol=code,
                    period='daily',
                    adjust='qfq',
                )
                if df is None or df.empty:
                    raise StockHistoryFetchError(f'{code}: empty dataframe')
                return self._df_to_bars(df, days)
            except StockHistoryFetchError:
                raise
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    backoff = self.base_backoff * (2 ** attempt)
                    log.warning(f'{code} retry {attempt + 1} after {backoff}s: {e}')
                    time.sleep(backoff)
        raise StockHistoryFetchError(f'{code} fetch failed: {last_err}')

    @staticmethod
    def _df_to_bars(df: pd.DataFrame, days: int) -> list[StockOhlcBar]:
        df = df.tail(days).reset_index(drop=True)
        bars: list[StockOhlcBar] = []
        for _, row in df.iterrows():
            dt = row['日期']
            d = dt.date() if hasattr(dt, 'date') else dt
            bars.append(StockOhlcBar(
                date=d,
                o=float(row['开盘']),
                h=float(row['最高']),
                l=float(row['最低']),
                c=float(row['收盘']),
                v=int(row['成交量']),
            ))
        return bars
```

- [ ] **Step 4: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_stock_history_provider.py -v 2>&1 | tail -15
```
Expected: 5 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/src/providers/stock_history_provider.py backend/tests/test_stock_history_provider.py
git commit -m "feat(providers): add StockHistoryProvider wrapping ak.stock_zh_a_hist with retry"
```

---

## Task 6: stocks_history_pipeline.py — 一次性 backfill

**Files:**
- Create: `backend/src/stocks_history_pipeline.py`
- Create: `backend/tests/test_stocks_history_pipeline.py`

- [ ] **Step 1: 写失败测试（端到端 mock 版）**

新建 `backend/tests/test_stocks_history_pipeline.py`：

```python
"""backfill pipeline 端到端测试（mock provider）"""
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import StockOhlcBar
from src.stocks_history_pipeline import run_history_backfill


def _bars(code: str, n: int = 75) -> list[StockOhlcBar]:
    base = date(2026, 1, 1).toordinal()
    return [
        StockOhlcBar(
            date=date.fromordinal(base + i),
            o=10.0 + i * 0.1, h=10.5 + i * 0.1, l=9.5 + i * 0.1,
            c=10.2 + i * 0.1, v=1000000 + i * 1000,
        )
        for i in range(n)
    ]


def test_backfill_writes_close_volume_series(tmp_path: Path):
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / '512480.json').write_text(json.dumps({
        'etf_code': '512480', 'etf_name': 'x',
        'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'TCL中环', 'weight': 8.5}],
    }))
    out_dir = tmp_path / 'stocks'

    fake_universe = ['002129', '603501']

    def fake_fetch(self, code, days):
        return _bars(code, days)

    with patch('src.stocks_history_pipeline._fetch_universe', return_value=fake_universe), \
         patch('src.providers.stock_history_provider.StockHistoryProvider.fetch_history', new=fake_fetch):
        report = run_history_backfill(
            holdings_dir=holdings_dir, out_dir=out_dir, days=75, max_workers=2,
        )

    assert (out_dir / 'close_series.json').exists()
    assert (out_dir / 'volume_series.json').exists()
    assert (out_dir / 'ohlc' / '002129.json').exists()
    # 603501 不在 holdings 内 → 不应写 ohlc
    assert not (out_dir / 'ohlc' / '603501.json').exists()
    assert report.success_count == 2
    assert report.failed_count == 0

    close_data = json.loads((out_dir / 'close_series.json').read_text())
    assert len(close_data['dates']) == 75
    assert '002129' in close_data['stocks']
    assert len(close_data['stocks']['002129']) == 75


def test_backfill_isolates_per_stock_failure(tmp_path: Path):
    (tmp_path / 'holdings').mkdir()
    (tmp_path / 'holdings' / 'x.json').write_text(json.dumps({
        'etf_code': 'x', 'etf_name': 'x', 'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00', 'top_holdings': [],
    }))

    def fake_fetch(self, code, days):
        if code == 'bad':
            from src.providers.stock_history_provider import StockHistoryFetchError
            raise StockHistoryFetchError('boom')
        return _bars(code, days)

    with patch('src.stocks_history_pipeline._fetch_universe', return_value=['ok1', 'bad', 'ok2']), \
         patch('src.providers.stock_history_provider.StockHistoryProvider.fetch_history', new=fake_fetch):
        report = run_history_backfill(
            holdings_dir=tmp_path / 'holdings',
            out_dir=tmp_path / 'stocks',
            days=75, max_workers=2,
        )

    assert report.success_count == 2
    assert report.failed_count == 1
    assert 'bad' in report.failed
```

- [ ] **Step 2: 跑测试，期望 ImportError**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_stocks_history_pipeline.py -v 2>&1 | tail -15
```
Expected: collection error

- [ ] **Step 3: 实现 stocks_history_pipeline.py**

新建 `backend/src/stocks_history_pipeline.py`：

```python
"""一次性历史 K 线 backfill 管道。

入口:
  python -m src.stocks_history_pipeline [--days 75] [--max-workers 4]

写入:
  data/stocks/close_series.json        全市场收盘价矩阵
  data/stocks/volume_series.json       全市场成交量矩阵
  data/stocks/ohlc/{code}.json         holdings 涉及个股 60 日 OHLC
  data/stocks/index.json               索引（含 ohlc_codes / last_trade_date）

注意：
- close_series / volume_series 包含全市场（~5000 只）用于 daily pipeline 算强度
- ohlc/*.json 仅写 holdings 涉及个股，避免 5000 文件
"""
from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak

from .models import StockOhlc, StockOhlcBar
from .providers.stock_history_provider import (
    StockHistoryFetchError,
    StockHistoryProvider,
)

log = logging.getLogger(__name__)


@dataclass
class BackfillReport:
    success: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def success_count(self) -> int: return len(self.success)
    @property
    def failed_count(self) -> int: return len(self.failed)


def _fetch_universe() -> list[str]:
    """从 akshare 拉全市场股票 code 列表。"""
    df = ak.stock_zh_a_spot_em()
    return df['代码'].astype(str).tolist()


def _read_holdings_codes(holdings_dir: Path) -> set[str]:
    codes: set[str] = set()
    for fp in holdings_dir.glob('*.json'):
        if fp.name == 'index.json':
            continue
        data = json.loads(fp.read_text(encoding='utf-8'))
        for h in data.get('top_holdings', []):
            codes.add(h['code'])
    return codes


def run_history_backfill(
    holdings_dir: Path,
    out_dir: Path,
    days: int = 75,
    max_workers: int = 4,
) -> BackfillReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    ohlc_dir = out_dir / 'ohlc'
    ohlc_dir.mkdir(exist_ok=True)

    holdings_codes = _read_holdings_codes(holdings_dir)
    universe = _fetch_universe()
    log.info(f'universe={len(universe)} holdings_codes={len(holdings_codes)}')

    provider = StockHistoryProvider()
    report = BackfillReport()
    results: dict[str, list[StockOhlcBar]] = {}

    def fetch_one(code: str) -> tuple[str, list[StockOhlcBar] | None, str | None]:
        try:
            bars = provider.fetch_history(code, days=days)
            return code, bars, None
        except StockHistoryFetchError as e:
            return code, None, str(e)
        except Exception as e:
            return code, None, f'unexpected: {e}'

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, c): c for c in universe}
        for fut in as_completed(futures):
            code, bars, err = fut.result()
            if bars is None:
                report.failed.append(code)
                log.warning(f'{code} failed: {err}')
                continue
            results[code] = bars
            report.success.append(code)

    # 收集所有出现过的日期（按出现顺序集中）
    all_dates = sorted({b.date for bars in results.values() for b in bars})
    all_dates = all_dates[-days:]
    date_idx = {d: i for i, d in enumerate(all_dates)}

    close_matrix: dict[str, list[float | None]] = {}
    volume_matrix: dict[str, list[int | None]] = {}
    for code, bars in results.items():
        closes: list[float | None] = [None] * len(all_dates)
        volumes: list[int | None] = [None] * len(all_dates)
        for b in bars:
            if b.date in date_idx:
                closes[date_idx[b.date]] = b.c
                volumes[date_idx[b.date]] = b.v
        close_matrix[code] = closes
        volume_matrix[code] = volumes

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (out_dir / 'close_series.json').write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': now,
        'dates': [d.isoformat() for d in all_dates],
        'stocks': close_matrix,
    }, ensure_ascii=False))
    (out_dir / 'volume_series.json').write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': now,
        'dates': [d.isoformat() for d in all_dates],
        'stocks': volume_matrix,
    }, ensure_ascii=False))

    # 写 holdings 涉及个股的 60 日 OHLC
    ohlc_codes: list[str] = []
    for code in sorted(holdings_codes & set(results.keys())):
        bars = results[code][-60:]
        snap = StockOhlc(
            code=code, name=code,
            generated_at=datetime.fromisoformat(now),
            bars=bars,
        )
        (ohlc_dir / f'{code}.json').write_text(
            snap.model_dump_json(),
            encoding='utf-8',
        )
        ohlc_codes.append(code)

    (out_dir / 'index.json').write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': now,
        'ohlc_codes': ohlc_codes,
        'last_trade_date': all_dates[-1].isoformat() if all_dates else None,
    }, ensure_ascii=False))

    log.info(f'backfill done: success={report.success_count} failed={report.failed_count}')
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--days', type=int, default=75)
    parser.add_argument('--max-workers', type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    run_history_backfill(
        holdings_dir=args.data_root / 'holdings',
        out_dir=args.data_root / 'stocks',
        days=args.days,
        max_workers=args.max_workers,
    )


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_stocks_history_pipeline.py -v 2>&1 | tail -15
```
Expected: 2 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/src/stocks_history_pipeline.py backend/tests/test_stocks_history_pipeline.py
git commit -m "feat(pipeline): add stocks_history_pipeline for one-time backfill"
```

---

## Task 7: stocks_daily_pipeline.py — 工作日盘后增量

**Files:**
- Create: `backend/src/stocks_daily_pipeline.py`
- Create: `backend/tests/test_stocks_daily_pipeline.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_stocks_daily_pipeline.py`：

```python
"""daily pipeline: 追加今日 spot → 算 indicators → 写文件"""
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.stocks_daily_pipeline import run_daily_pipeline


def _make_close_series(codes: list[str], n_days: int = 75) -> dict:
    dates = [f'2026-04-{i+1:02d}' for i in range(n_days)]
    return {
        'schema_version': '1.0',
        'generated_at': '2026-04-30T00:00:00+00:00',
        'dates': dates,
        'stocks': {code: [10.0 + i * 0.01 for i in range(n_days)] for code in codes},
    }


def _make_volume_series(codes: list[str], n_days: int = 75) -> dict:
    dates = [f'2026-04-{i+1:02d}' for i in range(n_days)]
    return {
        'schema_version': '1.0',
        'generated_at': '2026-04-30T00:00:00+00:00',
        'dates': dates,
        'stocks': {code: [1000000 + i * 1000 for i in range(n_days)] for code in codes},
    }


def _fake_spot_df(codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        '代码': codes,
        '名称': [f'股{c}' for c in codes],
        '最新价': [11.0 for _ in codes],
        '成交量': [2000000 for _ in codes],
    })


def test_daily_appends_today_and_writes_indicators(tmp_path: Path):
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / 'a.json').write_text(json.dumps({
        'etf_code': 'a', 'etf_name': 'a', 'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'TCL中环', 'weight': 8.5}],
    }))

    out_dir = tmp_path / 'stocks'
    out_dir.mkdir()
    (out_dir / 'ohlc').mkdir()
    universe_codes = ['002129', '603501', '600519']
    (out_dir / 'close_series.json').write_text(json.dumps(_make_close_series(universe_codes)))
    (out_dir / 'volume_series.json').write_text(json.dumps(_make_volume_series(universe_codes)))

    with patch('src.stocks_daily_pipeline._fetch_today_spot',
               return_value=_fake_spot_df(universe_codes)):
        run_daily_pipeline(
            holdings_dir=holdings_dir, out_dir=out_dir, today=date(2026, 6, 25),
        )

    # close_series 应追加 1 行（截窗 75 不变）
    cs = json.loads((out_dir / 'close_series.json').read_text())
    assert len(cs['dates']) == 75
    assert cs['dates'][-1] == '2026-06-25'
    assert cs['stocks']['002129'][-1] == 11.0

    # holdings_indicators 应只含 holdings 内的 002129
    hi = json.loads((out_dir / 'holdings_indicators.json').read_text())
    assert '002129' in hi['stocks']
    assert '603501' not in hi['stocks']  # 不在 holdings
    ind = hi['stocks']['002129']
    assert 'strength_60d' in ind
    assert 'rsi_14' in ind
    assert 'vol_ratio' in ind
    assert 'leader' in ind


def test_daily_handles_spot_fetch_failure_keeps_existing(tmp_path: Path):
    """spot 拉不到 → 保留昨日 holdings_indicators，不写空文件覆盖"""
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / 'a.json').write_text(json.dumps({
        'etf_code': 'a', 'etf_name': 'a', 'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'x', 'weight': 1.0}],
    }))
    out_dir = tmp_path / 'stocks'
    out_dir.mkdir()
    (out_dir / 'ohlc').mkdir()
    (out_dir / 'close_series.json').write_text(json.dumps(_make_close_series(['002129'])))
    (out_dir / 'volume_series.json').write_text(json.dumps(_make_volume_series(['002129'])))

    existing = {'schema_version': '1.0', 'generated_at': 'old',
                'stocks': {'002129': {'name': 'x', 'strength_60d': 50,
                                       'strength_20d': 50, 'rsi_14': 50.0,
                                       'vol_ratio': 1.0, 'leader': ''}}}
    (out_dir / 'holdings_indicators.json').write_text(json.dumps(existing))

    with patch('src.stocks_daily_pipeline._fetch_today_spot',
               side_effect=RuntimeError('akshare down')):
        run_daily_pipeline(
            holdings_dir=holdings_dir, out_dir=out_dir, today=date(2026, 6, 25),
        )

    # 文件应保持原值
    hi = json.loads((out_dir / 'holdings_indicators.json').read_text())
    assert hi['generated_at'] == 'old'


def test_daily_includes_leader_field(tmp_path: Path):
    """leader 字段必须存在且为合法值"""
    holdings_dir = tmp_path / 'holdings'
    holdings_dir.mkdir()
    (holdings_dir / 'a.json').write_text(json.dumps({
        'etf_code': 'a', 'etf_name': 'a', 'disclosure_date': '2026-03-31',
        'fetched_at': '2026-06-23T00:00:00+00:00',
        'top_holdings': [{'code': '002129', 'name': 'x', 'weight': 1.0}],
    }))
    out_dir = tmp_path / 'stocks'
    out_dir.mkdir()
    (out_dir / 'ohlc').mkdir()
    (out_dir / 'close_series.json').write_text(json.dumps(_make_close_series(['002129'])))
    (out_dir / 'volume_series.json').write_text(json.dumps(_make_volume_series(['002129'])))

    with patch('src.stocks_daily_pipeline._fetch_today_spot',
               return_value=_fake_spot_df(['002129'])):
        run_daily_pipeline(
            holdings_dir=holdings_dir, out_dir=out_dir, today=date(2026, 6, 25),
        )

    hi = json.loads((out_dir / 'holdings_indicators.json').read_text())
    leader = hi['stocks']['002129']['leader']
    assert leader in ('⭐⭐⭐', '⭐⭐', '⭐', '')
```

- [ ] **Step 2: 跑测试，期望 ImportError**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_stocks_daily_pipeline.py -v 2>&1 | tail -15
```
Expected: collection error

- [ ] **Step 3: 实现 stocks_daily_pipeline.py**

新建 `backend/src/stocks_daily_pipeline.py`：

```python
"""工作日盘后 daily 增量管道。

入口:
  python -m src.stocks_daily_pipeline [--data-root ./data]

步骤:
  1) 读 data/stocks/close_series.json + volume_series.json
  2) 拉今日 ak.stock_zh_a_spot_em → 追加一行 → 截窗 75
  3) 全市场批量算 r_5d / r_20d / r_60d → batch_strength
  4) 遍历 holdings 个股算 RSI / 量比 / leader
  5) 写 close_series / volume_series / holdings_indicators / ohlc/{code} / index
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import cast

import akshare as ak
import numpy as np
import pandas as pd

from .scoring.leader_rule import classify_leader
from .scoring.stock_indicators import compute_rsi, compute_volume_ratio
from .scoring.strength import batch_strength_per_dim

log = logging.getLogger(__name__)

WINDOW_DAYS = 75
K_SIGMOID = 2.0


def _fetch_today_spot() -> pd.DataFrame:
    return ak.stock_zh_a_spot_em()


def _read_holdings_codes(holdings_dir: Path) -> set[str]:
    codes: set[str] = set()
    for fp in holdings_dir.glob('*.json'):
        if fp.name == 'index.json':
            continue
        data = json.loads(fp.read_text(encoding='utf-8'))
        for h in data.get('top_holdings', []):
            codes.add(h['code'])
    return codes


def _read_holdings_names(holdings_dir: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for fp in holdings_dir.glob('*.json'):
        if fp.name == 'index.json':
            continue
        data = json.loads(fp.read_text(encoding='utf-8'))
        for h in data.get('top_holdings', []):
            names[h['code']] = h['name']
    return names


def _append_series(series_data: dict, today: date, today_values: dict[str, float | int | None]) -> dict:
    """追加今日一格，截窗保留尾部 WINDOW_DAYS 行。"""
    new_dates = series_data['dates'] + [today.isoformat()]
    new_dates = new_dates[-WINDOW_DAYS:]
    new_stocks: dict[str, list] = {}
    for code, hist in series_data['stocks'].items():
        appended = hist + [today_values.get(code)]
        new_stocks[code] = appended[-WINDOW_DAYS:]
    # 处理今日新增的股（之前 series 没有）
    for code, val in today_values.items():
        if code not in new_stocks:
            n_existing = len(new_dates) - 1
            new_stocks[code] = [None] * n_existing + [val]
            new_stocks[code] = new_stocks[code][-WINDOW_DAYS:]
    series_data['dates'] = new_dates
    series_data['stocks'] = new_stocks
    return series_data


def _compute_n_day_return(closes: list[float | None], n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    today = closes[-1]
    past = closes[-n - 1]
    if today is None or past is None or past <= 0:
        return None
    return (today - past) / past


def run_daily_pipeline(
    holdings_dir: Path,
    out_dir: Path,
    today: date | None = None,
) -> None:
    today = today or date.today()
    close_path = out_dir / 'close_series.json'
    volume_path = out_dir / 'volume_series.json'
    indicators_path = out_dir / 'holdings_indicators.json'

    close_data = json.loads(close_path.read_text(encoding='utf-8'))
    volume_data = json.loads(volume_path.read_text(encoding='utf-8'))

    # 拉今日 spot；失败则不覆盖现有 indicators
    try:
        spot_df = _fetch_today_spot()
    except Exception as e:
        log.error(f'spot fetch failed: {e}; keeping existing indicators untouched')
        return

    today_close = {str(r['代码']): float(r['最新价']) for _, r in spot_df.iterrows()
                   if pd.notna(r['最新价'])}
    today_volume = {str(r['代码']): int(r['成交量']) for _, r in spot_df.iterrows()
                    if pd.notna(r['成交量'])}

    close_data = _append_series(close_data, today, today_close)  # type: ignore[arg-type]
    volume_data = _append_series(volume_data, today, today_volume)  # type: ignore[arg-type]

    # 计算全市场强度
    universe = list(close_data['stocks'].keys())
    r_60d_arr = np.array([
        _compute_n_day_return(close_data['stocks'][c], 60) for c in universe
    ], dtype=float)
    r_20d_arr = np.array([
        _compute_n_day_return(close_data['stocks'][c], 20) for c in universe
    ], dtype=float)
    # NaN 替换：Python None → np.nan
    r_60d_arr = np.array([np.nan if v is None else v for v in r_60d_arr], dtype=float)
    r_20d_arr = np.array([np.nan if v is None else v for v in r_20d_arr], dtype=float)

    s60 = batch_strength_per_dim(r_60d_arr, k=K_SIGMOID, days_in_dim=60)
    s20 = batch_strength_per_dim(r_20d_arr, k=K_SIGMOID, days_in_dim=20)
    s60_map = dict(zip(universe, s60))
    s20_map = dict(zip(universe, s20))

    # 遍历 holdings 算 indicators
    holdings_codes = _read_holdings_codes(holdings_dir)
    holdings_names = _read_holdings_names(holdings_dir)
    indicators: dict[str, dict] = {}
    for code in holdings_codes:
        if code not in close_data['stocks']:
            continue
        closes = close_data['stocks'][code]
        volumes = volume_data['stocks'].get(code, [])
        s60_v = s60_map.get(code)
        s20_v = s20_map.get(code)
        s60_int: int | None = None if (s60_v is None or np.isnan(s60_v)) else int(s60_v)
        s20_int: int | None = None if (s20_v is None or np.isnan(s20_v)) else int(s20_v)
        rsi = compute_rsi(closes)
        vr = compute_volume_ratio(volumes)
        leader = classify_leader(s60_int, rsi)
        indicators[code] = {
            'name': holdings_names.get(code, code),
            'strength_60d': s60_int,
            'strength_20d': s20_int,
            'rsi_14': rsi,
            'vol_ratio': vr,
            'leader': leader,
        }

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    indicators_path.write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': now,
        'stocks': indicators,
    }, ensure_ascii=False))
    close_path.write_text(json.dumps(close_data, ensure_ascii=False))
    volume_path.write_text(json.dumps(volume_data, ensure_ascii=False))

    # 更新 holdings 个股的 60 日 OHLC（基于 close_series + volume_series 末 60 行重建）
    # 注：daily 不带 OHLC（仅 close + volume），所以 ohlc 文件仅在 backfill 时生成。
    # 此处可选刷新 generated_at，但暂时保持不动以避免无意义 commit。

    # 更新 index
    index_path = out_dir / 'index.json'
    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding='utf-8'))
    else:
        idx = {'schema_version': '1.0', 'ohlc_codes': []}
    idx['generated_at'] = now
    idx['last_trade_date'] = today.isoformat()
    index_path.write_text(json.dumps(idx, ensure_ascii=False))
    log.info(f'daily done: indicators={len(indicators)} universe={len(universe)}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    run_daily_pipeline(
        holdings_dir=args.data_root / 'holdings',
        out_dir=args.data_root / 'stocks',
    )


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_stocks_daily_pipeline.py -v 2>&1 | tail -15
```
Expected: 3 PASS

- [ ] **Step 5: 跑全部 backend 测试确保未影响既有**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -5
```
Expected: 所有测试 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/src/stocks_daily_pipeline.py backend/tests/test_stocks_daily_pipeline.py
git commit -m "feat(pipeline): add stocks_daily_pipeline with batch strength + indicators"
```

---

## Task 8: CI workflows + deploy paths 调整

**Files:**
- Create: `.github/workflows/stocks-history-backfill.yml`
- Create: `.github/workflows/stocks-daily.yml`
- Modify: `.github/workflows/deploy-frontend.yml`

- [ ] **Step 1: 先读取 deploy-frontend.yml 当前 paths**

```bash
cat /Users/dreambt/sources/etf-radar/.github/workflows/deploy-frontend.yml
```
记录现有 `on.push.paths` 列表，准备追加排除项。

- [ ] **Step 2: 创建 stocks-history-backfill.yml**

新建 `.github/workflows/stocks-history-backfill.yml`：

```yaml
name: stocks-history-backfill

on:
  workflow_dispatch:
    inputs:
      days:
        description: '回溯天数（默认 75，给 60 日指标留 buffer）'
        default: '75'
        required: true
      max_workers:
        description: 'akshare 并发数（默认 4，实测安全上限 3-5）'
        default: '4'
        required: true

permissions:
  contents: write

concurrency:
  group: stocks-history-backfill

jobs:
  backfill:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.DATA_BOT_PAT }}
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install uv
        run: pip install uv
      - name: Install deps
        run: cd backend && uv sync --all-extras
      - name: Run backfill
        run: |
          cd backend && uv run python -m src.stocks_history_pipeline \
            --data-root ../data \
            --days ${{ inputs.days }} \
            --max-workers ${{ inputs.max_workers }}
      - name: Commit & push
        run: |
          git config user.name "data-bot"
          git config user.email "data-bot@users.noreply.github.com"
          git add data/stocks/
          if git diff --cached --quiet; then
            echo "no changes"
          else
            git commit -m "data: stocks history backfill $(date -u +%FT%TZ)"
            git push
          fi
```

- [ ] **Step 3: 创建 stocks-daily.yml**

新建 `.github/workflows/stocks-daily.yml`：

```yaml
name: stocks-daily

on:
  schedule:
    # UTC 08:30 = BJT 16:30，A 股收盘后 30 min
    - cron: '30 8 * * 1-5'
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: stocks-daily

jobs:
  daily:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.DATA_BOT_PAT }}
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install uv
        run: pip install uv
      - name: Install deps
        run: cd backend && uv sync --all-extras
      - name: Run daily pipeline
        run: cd backend && uv run python -m src.stocks_daily_pipeline --data-root ../data
      - name: Commit & push
        run: |
          git config user.name "data-bot"
          git config user.email "data-bot@users.noreply.github.com"
          git add data/stocks/
          if git diff --cached --quiet; then
            echo "no changes"
          else
            git commit -m "data: stocks daily $(date -u +%FT%TZ)"
            git push
          fi
```

- [ ] **Step 4: 调整 deploy-frontend.yml**

打开 `.github/workflows/deploy-frontend.yml`，在 `on.push.paths` 列表末尾追加：

```yaml
      - '!data/stocks/close_series.json'
      - '!data/stocks/volume_series.json'
```

确保 backend-only 文件被显式排除（不触发 deploy）。

- [ ] **Step 5: 用 yamllint 或 actionlint 验证（如果可用）**

```bash
cd /Users/dreambt/sources/etf-radar && find .github/workflows -name "stocks-*.yml" -exec python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" {} \;
```
Expected: 无报错

- [ ] **Step 6: 提交**

```bash
git add .github/workflows/stocks-history-backfill.yml .github/workflows/stocks-daily.yml .github/workflows/deploy-frontend.yml
git commit -m "ci(stocks): add backfill + daily workflows; exclude backend-only series from deploy"
```

---

## Task 9: 前端类型 + dataUrls + 阈值常量

**Files:**
- Create: `frontend/src/types/stockIndicators.ts`
- Modify: `frontend/src/types/holdings.ts`
- Modify: `frontend/src/lib/dataUrls.ts`
- Create: `frontend/src/lib/stocks/indicatorThresholds.ts`

- [ ] **Step 1: 创建 stockIndicators.ts**

新建 `frontend/src/types/stockIndicators.ts`：

```typescript
/**
 * 后端数据契约（与 backend Pydantic models 对齐）：
 *   StockIndicators ↔ data/stocks/holdings_indicators.json::stocks[code]
 *   StockOhlcBar / StockOhlc ↔ data/stocks/ohlc/{code}.json
 */

export type LeaderStar = '⭐⭐⭐' | '⭐⭐' | '⭐' | '';

export interface StockIndicators {
  name: string;
  strength_60d: number | null;
  strength_20d: number | null;
  rsi_14: number | null;
  vol_ratio: number | null;
  leader: LeaderStar;
}

export interface HoldingsIndicatorsFile {
  schema_version: string;
  generated_at: string;
  stocks: Record<string, StockIndicators>;
}

export interface StockOhlcBar {
  date: string;       // YYYY-MM-DD
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
```

- [ ] **Step 2: 扩展 AggregatedStock**

修改 `frontend/src/types/holdings.ts`，在文件末尾追加：

```typescript

import type { StockIndicators } from './stockIndicators';

// 注：AggregatedStock 在 Phase 2 加入 indicators 字段
// 旧 export 改为 interface 扩展形式：
declare module './holdings' {
  // 占位，实际通过修改下方 interface 实现
}
```

实际操作方式是直接 Edit `AggregatedStock` interface（如下）。**用 Edit 工具，old_string 是 Phase 1 完整定义，new_string 加 indicators 字段**：

```typescript
export interface AggregatedStock {
  code: string;
  name: string;
  cumulativeWeight: number;
  sourceEtfs: string[];
  spot: StockSpot | null;
  indicators?: StockIndicators;  // Phase 2 新增，可选；缺失时表格显示 "—"
}
```

并在文件顶部 import 加入 `import type { StockIndicators } from './stockIndicators';`

- [ ] **Step 3: 扩展 dataUrls.ts**

修改 `frontend/src/lib/dataUrls.ts`，在 `holdingsEtfUrl` 之后追加：

```typescript

// Phase 2 个股指标
export const STOCKS_URLS = {
  holdingsIndicators: `${BASE}stocks/holdings_indicators.json`,
  index: `${BASE}stocks/index.json`,
} as const;

export const stockOhlcUrl = (stockCode: string): string =>
  `${BASE}stocks/ohlc/${stockCode}.json`;
```

- [ ] **Step 4: 创建阈值常量文件**

新建 `frontend/src/lib/stocks/indicatorThresholds.ts`：

```typescript
/**
 * Phase 2 指标阈值集中常量。
 * 修改阈值仅在此文件，避免散落在 Badge / structureInsight / leaderRule 多处。
 */

export interface StrengthTier {
  min: number;
  label: string;
  color: string;   // tailwind class
}

export const STRENGTH_TIERS: StrengthTier[] = [
  { min: 90, label: '极强', color: 'bg-red-100 text-red-700' },
  { min: 80, label: '强',   color: 'bg-orange-100 text-orange-700' },
  { min: 60, label: '中性', color: 'bg-gray-100 text-gray-600' },
  { min: 40, label: '偏弱', color: 'bg-blue-100 text-blue-700' },
  { min: 0,  label: '弱',   color: 'bg-blue-200 text-blue-800' },
];

export function strengthTier(value: number): StrengthTier {
  return STRENGTH_TIERS.find(t => value >= t.min) ?? STRENGTH_TIERS[STRENGTH_TIERS.length - 1];
}

export const RSI_ZONES = {
  overbought: 70,
  bullishTop: 65,
  bullishBottom: 50,
  oversold: 30,
} as const;

export function rsiColor(value: number): string {
  if (value >= RSI_ZONES.overbought) return 'bg-red-100 text-red-700';
  if (value >= RSI_ZONES.bullishBottom) return 'bg-orange-100 text-orange-700';
  if (value <= RSI_ZONES.oversold) return 'bg-blue-100 text-blue-700';
  return 'bg-gray-100 text-gray-600';
}

export const VOL_RATIO_THRESHOLDS = {
  high: 2.0,
  low: 0.5,
} as const;

export function volRatioColor(value: number): string {
  if (value >= VOL_RATIO_THRESHOLDS.high) return 'bg-red-100 text-red-700';
  if (value <= VOL_RATIO_THRESHOLDS.low) return 'bg-blue-100 text-blue-700';
  return 'bg-gray-100 text-gray-600';
}
```

- [ ] **Step 5: 跑 typecheck 与 lint**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -20
cd /Users/dreambt/sources/etf-radar/frontend && npx eslint src/types/stockIndicators.ts src/types/holdings.ts src/lib/dataUrls.ts src/lib/stocks/indicatorThresholds.ts 2>&1 | tail -10
```
Expected: 0 errors

- [ ] **Step 6: 提交**

```bash
git add frontend/src/types/stockIndicators.ts frontend/src/types/holdings.ts frontend/src/lib/dataUrls.ts frontend/src/lib/stocks/indicatorThresholds.ts
git commit -m "feat(stocks): add indicator types + URLs + threshold constants"
```

---

## Task 10: 前端 leaderRank + structureInsight 工具

**Files:**
- Create: `frontend/src/lib/stocks/leaderRank.ts`
- Create: `frontend/src/lib/stocks/structureInsight.ts`
- Create: `frontend/src/lib/stocks/__tests__/leaderRank.test.ts`
- Create: `frontend/src/lib/stocks/__tests__/structureInsight.test.ts`

- [ ] **Step 1: 写 leaderRank 失败测试**

新建 `frontend/src/lib/stocks/__tests__/leaderRank.test.ts`：

```typescript
import { describe, it, expect } from 'vitest';
import { leaderRank, compareLeader } from '../leaderRank';

describe('leaderRank', () => {
  it('returns higher rank for more stars', () => {
    expect(leaderRank('⭐⭐⭐')).toBeGreaterThan(leaderRank('⭐⭐'));
    expect(leaderRank('⭐⭐')).toBeGreaterThan(leaderRank('⭐'));
    expect(leaderRank('⭐')).toBeGreaterThan(leaderRank(''));
  });
  it('empty has lowest rank', () => {
    expect(leaderRank('')).toBe(0);
  });
});

describe('compareLeader', () => {
  it('sorts ⭐⭐⭐ before ⭐⭐ before ⭐ before empty', () => {
    const arr: Array<'⭐⭐⭐' | '⭐⭐' | '⭐' | ''> = ['', '⭐', '⭐⭐⭐', '⭐⭐'];
    arr.sort((a, b) => compareLeader(b, a));
    expect(arr).toEqual(['⭐⭐⭐', '⭐⭐', '⭐', '']);
  });
});
```

- [ ] **Step 2: 写 structureInsight 失败测试**

新建 `frontend/src/lib/stocks/__tests__/structureInsight.test.ts`：

```typescript
import { describe, it, expect } from 'vitest';
import { diagnoseStructure } from '../structureInsight';
import type { AggregatedStock } from '@/types/holdings';

function s(code: string, strength60: number | null): AggregatedStock {
  return {
    code, name: code, cumulativeWeight: 1, sourceEtfs: ['x'], spot: null,
    indicators: {
      name: code, strength_60d: strength60, strength_20d: null,
      rsi_14: null, vol_ratio: null, leader: '',
    },
  };
}

describe('diagnoseStructure', () => {
  it('head_led: 1-2 强股带动', () => {
    const stocks = [s('a', 90), s('b', 50), s('c', 45), s('d', 40), s('e', 35)];
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('head_led');
    expect(r.text).toContain('龙头带动');
  });

  it('broad_strength: ≥6 只 strength ≥ 70', () => {
    const stocks = ['a', 'b', 'c', 'd', 'e', 'f'].map(c => s(c, 75));
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('broad_strength');
    expect(r.text).toContain('全面走强');
  });

  it('divergent: 强度方差大无明显头部', () => {
    const stocks = [s('a', 85), s('b', 70), s('c', 60), s('d', 30), s('e', 20)];
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('divergent');
  });

  it('weak: 均值 < 50', () => {
    const stocks = ['a', 'b', 'c', 'd', 'e'].map(c => s(c, 40));
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('weak');
    expect(r.text).toContain('偏弱');
  });

  it('no_data: 全部 strength_60d 为 null', () => {
    const stocks = ['a', 'b'].map(c => s(c, null));
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('no_data');
  });
});
```

- [ ] **Step 3: 跑测试，期望全失败（模块不存在）**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/stocks/__tests__ 2>&1 | grep -E "(FAIL|×|Cannot find)" | head -10
```
Expected: Cannot find module errors

- [ ] **Step 4: 实现 leaderRank.ts**

新建 `frontend/src/lib/stocks/leaderRank.ts`：

```typescript
import type { LeaderStar } from '@/types/stockIndicators';

/**
 * 龙头标签的可排序整数表示。
 * 高分排前：⭐⭐⭐=3, ⭐⭐=2, ⭐=1, ''=0
 */
export function leaderRank(s: LeaderStar): number {
  switch (s) {
    case '⭐⭐⭐': return 3;
    case '⭐⭐': return 2;
    case '⭐': return 1;
    default: return 0;
  }
}

export function compareLeader(a: LeaderStar, b: LeaderStar): number {
  return leaderRank(a) - leaderRank(b);
}
```

- [ ] **Step 5: 实现 structureInsight.ts**

新建 `frontend/src/lib/stocks/structureInsight.ts`：

```typescript
import type { AggregatedStock } from '@/types/holdings';

export type ThemeStructure =
  | 'head_led'
  | 'broad_strength'
  | 'divergent'
  | 'weak'
  | 'no_data';

export interface StructureDiagnosis {
  type: ThemeStructure;
  text: string;
  validCount: number;
  meanStrength: number | null;
}

/**
 * 主题结构诊断（基于 strength_60d 分布）。
 *
 * 规则优先级（先匹配优先）：
 *   no_data: 全部 strength 为 null
 *   broad_strength: ≥ 6 只 strength ≥ 70
 *   head_led: 1-2 只 strength ≥ 80 且其他 < 60
 *   weak: 均值 < 50
 *   divergent: 其他情况（强弱分化）
 */
export function diagnoseStructure(stocks: AggregatedStock[]): StructureDiagnosis {
  const strengths = stocks
    .map(s => s.indicators?.strength_60d)
    .filter((v): v is number => v !== null && v !== undefined);

  if (strengths.length === 0) {
    return { type: 'no_data', text: '本主题暂无指标数据', validCount: 0, meanStrength: null };
  }

  const mean = strengths.reduce((a, b) => a + b, 0) / strengths.length;
  const strong = strengths.filter(v => v >= 70).length;
  const veryStrong = strengths.filter(v => v >= 80).length;
  const weak = strengths.filter(v => v < 60).length;

  if (strong >= 6) {
    return {
      type: 'broad_strength',
      text: `本主题 ${strong} 只股票强度 ≥ 70，全面走强`,
      validCount: strengths.length,
      meanStrength: Math.round(mean),
    };
  }
  if (veryStrong >= 1 && veryStrong <= 2 && weak >= strengths.length - veryStrong - 1) {
    return {
      type: 'head_led',
      text: `本主题由 ${veryStrong} 只龙头带动，其他成分股偏中性`,
      validCount: strengths.length,
      meanStrength: Math.round(mean),
    };
  }
  if (mean < 50) {
    return {
      type: 'weak',
      text: `本主题整体偏弱（均值 ${Math.round(mean)}），建议观望`,
      validCount: strengths.length,
      meanStrength: Math.round(mean),
    };
  }
  return {
    type: 'divergent',
    text: `本主题强度分化（均值 ${Math.round(mean)}，强者 ${veryStrong} 弱者 ${weak}），结构不健康`,
    validCount: strengths.length,
    meanStrength: Math.round(mean),
  };
}
```

- [ ] **Step 6: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/stocks/__tests__ 2>&1 | grep -E "(Test Files|Tests|FAIL|✓|×)" | tail -15
```
Expected: 9 PASS

- [ ] **Step 7: 提交**

```bash
git add frontend/src/lib/stocks/
git commit -m "feat(stocks): add leaderRank + structureInsight with tests"
```

---

## Task 11: 前端 hooks useStockIndicators + useStockOhlc

**Files:**
- Create: `frontend/src/lib/holdings/useStockIndicators.ts`
- Create: `frontend/src/lib/holdings/useStockOhlc.ts`
- Create: `frontend/src/lib/holdings/__tests__/useStockIndicators.test.ts`
- Create: `frontend/src/lib/holdings/__tests__/useStockOhlc.test.ts`

- [ ] **Step 1: 写 useStockIndicators 失败测试**

新建 `frontend/src/lib/holdings/__tests__/useStockIndicators.test.ts`：

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStockIndicators } from '../useStockIndicators';

let fetchSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => { fetchSpy = vi.spyOn(globalThis, 'fetch'); });
afterEach(() => { fetchSpy.mockRestore(); vi.clearAllMocks(); });

describe('useStockIndicators', () => {
  it('returns indicators map on success', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify({
      schema_version: '1.0', generated_at: '...',
      stocks: { '002129': { name: 'TCL中环', strength_60d: 87, strength_20d: 91,
                            rsi_14: 62.3, vol_ratio: 1.85, leader: '⭐⭐' } },
    })));
    const { result } = renderHook(() => useStockIndicators());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.get('002129')?.strength_60d).toBe(87);
  });

  it('returns empty map on 404', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('', { status: 404 }));
    const { result } = renderHook(() => useStockIndicators());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.size).toBe(0);
    expect(result.current.error).toBeNull();
  });
});
```

- [ ] **Step 2: 写 useStockOhlc 失败测试**

新建 `frontend/src/lib/holdings/__tests__/useStockOhlc.test.ts`：

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStockOhlc } from '../useStockOhlc';

let fetchSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => { fetchSpy = vi.spyOn(globalThis, 'fetch'); });
afterEach(() => { fetchSpy.mockRestore(); vi.clearAllMocks(); });

describe('useStockOhlc', () => {
  it('does not fetch when code is null', () => {
    renderHook(() => useStockOhlc(null));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('fetches OHLC for given code', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify({
      code: '002129', name: 'TCL中环', generated_at: '...',
      bars: [{ date: '2026-04-01', o: 12.3, h: 12.6, l: 12.2, c: 12.5, v: 100 }],
    })));
    const { result } = renderHook(() => useStockOhlc('002129'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data?.bars).toHaveLength(1);
  });
});
```

- [ ] **Step 3: 跑测试，期望全失败**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/holdings/__tests__/useStock 2>&1 | grep -E "(Cannot find|FAIL)" | head -10
```
Expected: module not found

- [ ] **Step 4: 实现 useStockIndicators.ts**

新建 `frontend/src/lib/holdings/useStockIndicators.ts`：

```typescript
import { useEffect, useState } from 'react';
import { STOCKS_URLS } from '@/lib/dataUrls';
import type { HoldingsIndicatorsFile, StockIndicators } from '@/types/stockIndicators';

interface UseStockIndicatorsResult {
  data: Map<string, StockIndicators>;
  loading: boolean;
  error: Error | null;
}

const EMPTY: Map<string, StockIndicators> = new Map();

export function useStockIndicators(): UseStockIndicatorsResult {
  const [data, setData] = useState<Map<string, StockIndicators>>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(STOCKS_URLS.holdingsIndicators)
      .then(res => {
        if (!res.ok) {
          if (res.status === 404) {
            // backfill 未跑过 / 数据缺失，静默返回空 Map
            return null;
          }
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json() as Promise<HoldingsIndicatorsFile>;
      })
      .then(payload => {
        if (cancelled) return;
        if (!payload) {
          setData(EMPTY);
        } else {
          setData(new Map(Object.entries(payload.stocks)));
        }
        setLoading(false);
      })
      .catch(e => {
        if (cancelled) return;
        setError(e as Error);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return { data, loading, error };
}
```

- [ ] **Step 5: 实现 useStockOhlc.ts**

新建 `frontend/src/lib/holdings/useStockOhlc.ts`：

```typescript
import { useEffect, useState } from 'react';
import { stockOhlcUrl } from '@/lib/dataUrls';
import type { StockOhlc } from '@/types/stockIndicators';

interface UseStockOhlcResult {
  data: StockOhlc | null;
  loading: boolean;
  error: Error | null;
}

const cache = new Map<string, StockOhlc>();

export function useStockOhlc(code: string | null): UseStockOhlcResult {
  const [data, setData] = useState<StockOhlc | null>(code ? cache.get(code) ?? null : null);
  const [loading, setLoading] = useState(code !== null && !cache.has(code));
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (code === null) {
      setData(null);
      setLoading(false);
      return;
    }
    const cached = cache.get(code);
    if (cached) {
      setData(cached);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetch(stockOhlcUrl(code))
      .then(res => {
        if (!res.ok) {
          if (res.status === 404) return null;
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json() as Promise<StockOhlc>;
      })
      .then(payload => {
        if (cancelled) return;
        if (payload) cache.set(code, payload);
        setData(payload);
        setLoading(false);
      })
      .catch(e => {
        if (cancelled) return;
        setError(e as Error);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [code]);

  return { data, loading, error };
}
```

- [ ] **Step 6: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/holdings/__tests__/useStock 2>&1 | grep -E "(Test Files|Tests|FAIL|✓|×)" | tail -10
```
Expected: 4 PASS

- [ ] **Step 7: 提交**

```bash
git add frontend/src/lib/holdings/useStockIndicators.ts frontend/src/lib/holdings/useStockOhlc.ts frontend/src/lib/holdings/__tests__/useStockIndicators.test.ts frontend/src/lib/holdings/__tests__/useStockOhlc.test.ts
git commit -m "feat(holdings): add useStockIndicators + useStockOhlc hooks"
```

---

## Task 12: 前端 3 个 Badge 组件

**Files:**
- Create: `frontend/src/components/stocks/StrengthBadge.tsx`
- Create: `frontend/src/components/stocks/RSIBadge.tsx`
- Create: `frontend/src/components/stocks/VolumeRatioBadge.tsx`

- [ ] **Step 1: 实现 StrengthBadge.tsx**

新建 `frontend/src/components/stocks/StrengthBadge.tsx`：

```tsx
import { strengthTier } from '@/lib/stocks/indicatorThresholds';
import { cn } from '@/lib/utils';

interface Props {
  value: number | null;
  className?: string;
}

export const StrengthBadge = ({ value, className }: Props) => {
  if (value === null || Number.isNaN(value)) {
    return <span className="text-gray-400">—</span>;
  }
  const tier = strengthTier(value);
  return (
    <span
      title={tier.label}
      className={cn(
        'inline-block px-2 py-0.5 rounded text-xs font-mono tabular-nums',
        tier.color,
        className,
      )}
    >
      {value}
    </span>
  );
};
```

- [ ] **Step 2: 实现 RSIBadge.tsx**

新建 `frontend/src/components/stocks/RSIBadge.tsx`：

```tsx
import { rsiColor } from '@/lib/stocks/indicatorThresholds';
import { cn } from '@/lib/utils';

interface Props {
  value: number | null;
  className?: string;
}

export const RSIBadge = ({ value, className }: Props) => {
  if (value === null || Number.isNaN(value)) {
    return <span className="text-gray-400">—</span>;
  }
  return (
    <span
      className={cn(
        'inline-block px-2 py-0.5 rounded text-xs font-mono tabular-nums',
        rsiColor(value),
        className,
      )}
    >
      {value.toFixed(1)}
    </span>
  );
};
```

- [ ] **Step 3: 实现 VolumeRatioBadge.tsx**

新建 `frontend/src/components/stocks/VolumeRatioBadge.tsx`：

```tsx
import { volRatioColor } from '@/lib/stocks/indicatorThresholds';
import { cn } from '@/lib/utils';

interface Props {
  value: number | null;
  className?: string;
}

export const VolumeRatioBadge = ({ value, className }: Props) => {
  if (value === null || Number.isNaN(value)) {
    return <span className="text-gray-400">—</span>;
  }
  return (
    <span
      className={cn(
        'inline-block px-2 py-0.5 rounded text-xs font-mono tabular-nums',
        volRatioColor(value),
        className,
      )}
    >
      {value.toFixed(2)}
    </span>
  );
};
```

- [ ] **Step 4: 跑 typecheck**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -10
```
Expected: 0 errors

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/stocks/StrengthBadge.tsx frontend/src/components/stocks/RSIBadge.tsx frontend/src/components/stocks/VolumeRatioBadge.tsx
git commit -m "feat(stocks): add StrengthBadge / RSIBadge / VolumeRatioBadge"
```

---

## Task 13: MiniKlineChart 组件（SVG 原生）

**Files:**
- Create: `frontend/src/components/stocks/MiniKlineChart.tsx`
- Create: `frontend/src/components/stocks/__tests__/MiniKlineChart.test.tsx`

- [ ] **Step 1: 写失败测试**

新建 `frontend/src/components/stocks/__tests__/MiniKlineChart.test.tsx`：

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MiniKlineChart } from '../MiniKlineChart';

let fetchSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => { fetchSpy = vi.spyOn(globalThis, 'fetch'); });
afterEach(() => { fetchSpy.mockRestore(); vi.clearAllMocks(); });

describe('MiniKlineChart', () => {
  it('shows loading then renders SVG with bars', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify({
      code: '002129', name: 'TCL', generated_at: '...',
      bars: [
        { date: '2026-04-01', o: 10, h: 11, l: 9.5, c: 10.5, v: 100 },
        { date: '2026-04-02', o: 10.5, h: 11.2, l: 10.3, c: 10.8, v: 110 },
        { date: '2026-04-03', o: 10.8, h: 11, l: 10.5, c: 10.6, v: 90 },
      ],
    })));
    const { container } = render(<MiniKlineChart code="002129" />);
    await waitFor(() => expect(container.querySelector('svg')).toBeInTheDocument());
    const rects = container.querySelectorAll('svg rect');
    expect(rects.length).toBeGreaterThanOrEqual(3);
  });

  it('shows "数据不足" when bars < 5', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify({
      code: '002129', name: 'x', generated_at: '...',
      bars: [{ date: '2026-04-01', o: 10, h: 11, l: 9, c: 10.5, v: 100 }],
    })));
    render(<MiniKlineChart code="002129" />);
    await waitFor(() => expect(screen.getByText(/数据不足/)).toBeInTheDocument());
  });

  it('shows "无数据" on 404', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('', { status: 404 }));
    render(<MiniKlineChart code="002129" />);
    await waitFor(() => expect(screen.getByText(/无数据/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 跑测试，期望失败**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/stocks/__tests__/MiniKlineChart 2>&1 | grep -E "(Cannot find|FAIL|×)" | head -5
```
Expected: module not found

- [ ] **Step 3: 实现 MiniKlineChart.tsx**

新建 `frontend/src/components/stocks/MiniKlineChart.tsx`：

```tsx
import { useStockOhlc } from '@/lib/holdings/useStockOhlc';
import type { StockOhlcBar } from '@/types/stockIndicators';

interface Props {
  code: string;
  width?: number;
  height?: number;
}

const PAD = 4;

export const MiniKlineChart = ({ code, width = 160, height = 80 }: Props) => {
  const { data, loading } = useStockOhlc(code);

  if (loading) {
    return <div className="text-xs text-gray-400 px-1 py-2">加载中...</div>;
  }
  if (!data) {
    return <div className="text-xs text-gray-400 px-1 py-2">无数据</div>;
  }
  if (data.bars.length < 5) {
    return <div className="text-xs text-gray-400 px-1 py-2">数据不足</div>;
  }

  const bars = data.bars.slice(-60);
  const allHighs = bars.map(b => b.h);
  const allLows = bars.map(b => b.l);
  const maxP = Math.max(...allHighs);
  const minP = Math.min(...allLows);
  const range = maxP - minP || 1;
  const innerW = width - 2 * PAD;
  const innerH = height - 2 * PAD;
  const barW = innerW / bars.length;
  const candleW = Math.max(1, barW * 0.7);

  const yFor = (price: number) =>
    PAD + (1 - (price - minP) / range) * innerH;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="bg-white rounded border border-gray-200 shadow-sm"
      aria-label={`${data.name} 60 日 K 线`}
    >
      {bars.map((b: StockOhlcBar, i: number) => {
        const cx = PAD + i * barW + barW / 2;
        const yHigh = yFor(b.h);
        const yLow = yFor(b.l);
        const yOpen = yFor(b.o);
        const yClose = yFor(b.c);
        const up = b.c >= b.o;
        const color = up ? '#e11d48' : '#16a34a';  // 中国市场红涨绿跌
        const bodyY = Math.min(yOpen, yClose);
        const bodyH = Math.max(1, Math.abs(yClose - yOpen));
        return (
          <g key={`${b.date}-${i}`}>
            <line
              x1={cx} x2={cx} y1={yHigh} y2={yLow}
              stroke={color} strokeWidth={1}
            />
            <rect
              x={cx - candleW / 2}
              y={bodyY}
              width={candleW}
              height={bodyH}
              fill={color}
            />
          </g>
        );
      })}
    </svg>
  );
};
```

- [ ] **Step 4: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/stocks/__tests__/MiniKlineChart 2>&1 | grep -E "(Test Files|Tests|FAIL|✓|×)" | tail -10
```
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/stocks/MiniKlineChart.tsx frontend/src/components/stocks/__tests__/MiniKlineChart.test.tsx
git commit -m "feat(stocks): add MiniKlineChart (SVG native, 60-day OHLC)"
```

---

## Task 14: ThemeStructureSummary 组件

**Files:**
- Create: `frontend/src/components/stocks/ThemeStructureSummary.tsx`
- Create: `frontend/src/components/stocks/__tests__/ThemeStructureSummary.test.tsx`

- [ ] **Step 1: 写失败测试**

新建 `frontend/src/components/stocks/__tests__/ThemeStructureSummary.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ThemeStructureSummary } from '../ThemeStructureSummary';
import type { AggregatedStock } from '@/types/holdings';

function s(code: string, strength60: number | null, leader = ''): AggregatedStock {
  return {
    code, name: code, cumulativeWeight: 1, sourceEtfs: ['x'], spot: null,
    indicators: {
      name: code, strength_60d: strength60, strength_20d: null,
      rsi_14: null, vol_ratio: null,
      leader: leader as '⭐⭐⭐' | '⭐⭐' | '⭐' | '',
    },
  };
}

describe('ThemeStructureSummary', () => {
  it('renders diagnosis text', () => {
    const stocks = ['a', 'b', 'c', 'd', 'e', 'f'].map(c => s(c, 75));
    render(<ThemeStructureSummary stocks={stocks} />);
    expect(screen.getByText(/全面走强/)).toBeInTheDocument();
  });

  it('shows 3-star leader count and ratio', () => {
    const stocks = [s('a', 90, '⭐⭐⭐'), s('b', 80, '⭐⭐'), s('c', 60)];
    render(<ThemeStructureSummary stocks={stocks} />);
    expect(screen.getByText(/⭐⭐⭐.*1/)).toBeInTheDocument();
  });

  it('shows fallback when no indicators', () => {
    const stocks = [{ code: 'x', name: 'x', cumulativeWeight: 1,
                      sourceEtfs: ['x'], spot: null } as AggregatedStock];
    render(<ThemeStructureSummary stocks={stocks} />);
    expect(screen.getByText(/暂无指标数据/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试，期望失败**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/stocks/__tests__/ThemeStructureSummary 2>&1 | grep -E "(Cannot find|FAIL|×)" | head -5
```

- [ ] **Step 3: 实现 ThemeStructureSummary.tsx**

新建 `frontend/src/components/stocks/ThemeStructureSummary.tsx`：

```tsx
import { useMemo } from 'react';
import type { AggregatedStock } from '@/types/holdings';
import { diagnoseStructure } from '@/lib/stocks/structureInsight';

interface Props {
  stocks: AggregatedStock[];
}

const STRUCTURE_COLOR: Record<string, string> = {
  head_led: 'border-orange-300 bg-orange-50 text-orange-900',
  broad_strength: 'border-red-300 bg-red-50 text-red-900',
  divergent: 'border-yellow-300 bg-yellow-50 text-yellow-900',
  weak: 'border-blue-300 bg-blue-50 text-blue-900',
  no_data: 'border-gray-300 bg-gray-50 text-gray-600',
};

export const ThemeStructureSummary = ({ stocks }: Props) => {
  const diag = useMemo(() => diagnoseStructure(stocks), [stocks]);
  const threeStarCount = useMemo(
    () => stocks.filter(s => s.indicators?.leader === '⭐⭐⭐').length,
    [stocks],
  );
  const total = stocks.length;
  const ratioPct = total > 0 ? Math.round((threeStarCount / total) * 100) : 0;

  return (
    <div
      className={`mb-3 p-3 border rounded ${STRUCTURE_COLOR[diag.type] ?? STRUCTURE_COLOR.no_data}`}
      aria-label="主题结构摘要"
    >
      <div className="text-sm font-medium">{diag.text}</div>
      {diag.type !== 'no_data' && (
        <div className="mt-1 text-xs text-gray-600">
          <span>⭐⭐⭐ {threeStarCount} 只 ({ratioPct}%)</span>
          {diag.meanStrength !== null && (
            <span className="ml-3">均值强度 {diag.meanStrength}</span>
          )}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: 跑测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/stocks/__tests__/ThemeStructureSummary 2>&1 | grep -E "(Test Files|Tests|FAIL|✓|×)" | tail -10
```
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/stocks/ThemeStructureSummary.tsx frontend/src/components/stocks/__tests__/ThemeStructureSummary.test.tsx
git commit -m "feat(stocks): add ThemeStructureSummary with diagnosis + ⭐⭐⭐ count"
```

---

## Task 15: aggregator 扩展 + StockTable 集成

**Files:**
- Modify: `frontend/src/lib/holdings/aggregator.ts`
- Modify: `frontend/src/lib/holdings/__tests__/aggregator.test.ts`（已存在或新建）
- Modify: `frontend/src/components/stocks/StockTable.tsx`

- [ ] **Step 1: 检查现有 aggregator 测试文件**

```bash
ls /Users/dreambt/sources/etf-radar/frontend/src/lib/holdings/__tests__/aggregator.test.ts 2>&1
```
若存在 → 在文件末尾追加测试；若不存在 → 创建。

- [ ] **Step 2: 写 aggregator 扩展测试**

在 `frontend/src/lib/holdings/__tests__/aggregator.test.ts` 中追加（若不存在则新建文件 + 写 import）：

```typescript
import { describe, it, expect } from 'vitest';
import { aggregateHoldings } from '../aggregator';
import type { EtfHoldingsSnapshot } from '@/types/holdings';
import type { StockIndicators } from '@/types/stockIndicators';

describe('aggregateHoldings with indicators', () => {
  it('joins indicators by code', () => {
    const snap: EtfHoldingsSnapshot = {
      etf_code: '512480', etf_name: 'x',
      disclosure_date: '2026-03-31', fetched_at: '2026-06-23T00:00:00+00:00',
      top_holdings: [{ code: '002129', name: 'TCL中环', weight: 8.5 }],
    };
    const indicators = new Map<string, StockIndicators>([
      ['002129', { name: 'TCL中环', strength_60d: 87, strength_20d: 91,
                   rsi_14: 62.3, vol_ratio: 1.85, leader: '⭐⭐' }],
    ]);
    const out = aggregateHoldings([snap], {}, indicators);
    expect(out[0].indicators?.strength_60d).toBe(87);
    expect(out[0].indicators?.leader).toBe('⭐⭐');
  });

  it('indicators undefined when missing', () => {
    const snap: EtfHoldingsSnapshot = {
      etf_code: 'x', etf_name: 'x',
      disclosure_date: '2026-03-31', fetched_at: '2026-06-23T00:00:00+00:00',
      top_holdings: [{ code: '999999', name: '无指标股', weight: 5.0 }],
    };
    const out = aggregateHoldings([snap], {}, new Map());
    expect(out[0].indicators).toBeUndefined();
  });

  it('works without indicators param (backward compat)', () => {
    const snap: EtfHoldingsSnapshot = {
      etf_code: 'x', etf_name: 'x',
      disclosure_date: '2026-03-31', fetched_at: '2026-06-23T00:00:00+00:00',
      top_holdings: [{ code: '002129', name: 'x', weight: 5.0 }],
    };
    const out = aggregateHoldings([snap], {});
    expect(out[0].indicators).toBeUndefined();
  });
});
```

- [ ] **Step 3: 跑测试，期望部分失败**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/holdings/__tests__/aggregator 2>&1 | grep -E "(FAIL|✓|×)" | head -10
```
Expected: 新加测试 FAIL（aggregateHoldings 签名不接受 indicators）

- [ ] **Step 4: 扩展 aggregator.ts**

修改 `frontend/src/lib/holdings/aggregator.ts` 函数签名与实现：

```typescript
import type {
  AggregatedStock,
  EtfHoldingsSnapshot,
  StockSpot,
} from '@/types/holdings';
import type { StockIndicators } from '@/types/stockIndicators';

/**
 * 把多个 ETF 的 top-N 持仓合并为唯一个股清单。
 * Phase 2 扩展：可选 indicators 参数（Map<code, StockIndicators>）
 * 在聚合时 join 到 .indicators 字段；跨主题股自然按 code 去重。
 */
export function aggregateHoldings(
  snapshots: EtfHoldingsSnapshot[],
  spots: Record<string, StockSpot>,
  indicators?: Map<string, StockIndicators>,
): AggregatedStock[] {
  const map = new Map<string, AggregatedStock>();

  for (const snap of snapshots) {
    for (const h of snap.top_holdings) {
      const existing = map.get(h.code);
      if (existing) {
        existing.cumulativeWeight += h.weight;
        if (!existing.sourceEtfs.includes(snap.etf_code)) {
          existing.sourceEtfs.push(snap.etf_code);
        }
      } else {
        map.set(h.code, {
          code: h.code,
          name: h.name,
          cumulativeWeight: h.weight,
          sourceEtfs: [snap.etf_code],
          spot: spots[h.code] ?? null,
          indicators: indicators?.get(h.code),
        });
      }
    }
  }

  return Array.from(map.values()).sort((a, b) => {
    if (b.cumulativeWeight !== a.cumulativeWeight) {
      return b.cumulativeWeight - a.cumulativeWeight;
    }
    return a.code.localeCompare(b.code);
  });
}
```

- [ ] **Step 5: 跑 aggregator 测试，期望全绿**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/holdings/__tests__/aggregator 2>&1 | grep -E "(Test Files|Tests|FAIL|✓|×)" | tail -10
```
Expected: 全部 PASS

- [ ] **Step 6: 扩展 StockTable.tsx**

完整重写 `frontend/src/components/stocks/StockTable.tsx`：

```tsx
import { useState } from 'react';
import type { AggregatedStock } from '@/types/holdings';
import { cn } from '@/lib/utils';
import { compareLeader } from '@/lib/stocks/leaderRank';
import { StrengthBadge } from './StrengthBadge';
import { RSIBadge } from './RSIBadge';
import { VolumeRatioBadge } from './VolumeRatioBadge';
import { MiniKlineChart } from './MiniKlineChart';

interface Props {
  stocks: AggregatedStock[];
}

const formatPct = (n: number | null): string => {
  if (n === null || Number.isNaN(n)) return '—';
  const pct = n * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
};

const formatWeight = (w: number): string => `${w.toFixed(1)}%`;

const formatPrice = (n: number | null): string => {
  if (n === null || Number.isNaN(n)) return '—';
  return n.toFixed(2);
};

// 默认排序：leader desc → strength_60d desc → cumulativeWeight desc
function sortByLeaderThenStrength(stocks: AggregatedStock[]): AggregatedStock[] {
  return [...stocks].sort((a, b) => {
    const la = a.indicators?.leader ?? '';
    const lb = b.indicators?.leader ?? '';
    const leaderDiff = compareLeader(lb, la);
    if (leaderDiff !== 0) return leaderDiff;
    const sa = a.indicators?.strength_60d ?? -1;
    const sb = b.indicators?.strength_60d ?? -1;
    if (sb !== sa) return sb - sa;
    return b.cumulativeWeight - a.cumulativeWeight;
  });
}

export const StockTable = ({ stocks }: Props) => {
  const sorted = sortByLeaderThenStrength(stocks);
  const [hoverCode, setHoverCode] = useState<string | null>(null);

  return (
    <div className="relative">
      <table className="w-full text-sm border-collapse">
        <thead className="bg-gray-100 text-xs text-gray-600">
          <tr>
            <th className="px-2 py-2 text-center w-12">#</th>
            <th className="px-2 py-2 text-center w-12">龙头</th>
            <th className="px-2 py-2 text-left">代码</th>
            <th className="px-2 py-2 text-left">名称</th>
            <th className="px-2 py-2 text-left">关联 ETF</th>
            <th className="px-2 py-2 text-right">权重</th>
            <th className="px-2 py-2 text-right">收盘</th>
            <th className="px-2 py-2 text-right">今日</th>
            <th className="px-2 py-2 text-center">60d</th>
            <th className="px-2 py-2 text-center">20d</th>
            <th className="px-2 py-2 text-center">RSI</th>
            <th className="px-2 py-2 text-center">量比</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s, idx) => {
            const r1d = s.spot?.r_1d ?? null;
            const ind = s.indicators;
            return (
              <tr
                key={s.code}
                className="border-b hover:bg-gray-50 relative"
                onMouseEnter={() => setHoverCode(s.code)}
                onMouseLeave={() => setHoverCode(prev => (prev === s.code ? null : prev))}
              >
                <td className="px-2 py-2 text-center text-gray-500">{idx + 1}</td>
                <td className="px-2 py-2 text-center text-sm">{ind?.leader ?? ''}</td>
                <td className="px-2 py-2 font-mono">{s.code}</td>
                <td className="px-2 py-2">{s.name}</td>
                <td className="px-2 py-2">
                  <div className="flex flex-wrap gap-1">
                    {s.sourceEtfs.map(etf => (
                      <span key={etf} className="px-1.5 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono">
                        {etf}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-2 py-2 text-right tabular-nums">{formatWeight(s.cumulativeWeight)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatPrice(s.spot?.close ?? null)}</td>
                <td className={cn(
                  'px-2 py-2 text-right tabular-nums',
                  r1d === null ? 'text-gray-400' : r1d >= 0 ? 'text-red-600' : 'text-green-600',
                )}>{formatPct(r1d)}</td>
                <td className="px-2 py-2 text-center">
                  <StrengthBadge value={ind?.strength_60d ?? null} />
                </td>
                <td className="px-2 py-2 text-center">
                  <StrengthBadge value={ind?.strength_20d ?? null} />
                </td>
                <td className="px-2 py-2 text-center">
                  <RSIBadge value={ind?.rsi_14 ?? null} />
                </td>
                <td className="px-2 py-2 text-center">
                  <VolumeRatioBadge value={ind?.vol_ratio ?? null} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {hoverCode && (
        <div
          className="hidden md:block absolute right-0 top-0 z-10 pointer-events-none"
          aria-label={`${hoverCode} K 线浮层`}
        >
          <MiniKlineChart code={hoverCode} />
        </div>
      )}
    </div>
  );
};
```

注：今日涨跌的颜色映射调整为中国市场惯例（红涨绿跌），与 MiniKlineChart 一致。

- [ ] **Step 7: 跑 frontend 全部测试，确保未破坏既有**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | grep -E "(Test Files|Tests|FAIL|×)" | tail -20
```
Expected: 全部 PASS（或仅 StocksPage 相关失败 — Task 16 修复）

- [ ] **Step 8: 提交**

```bash
git add frontend/src/lib/holdings/aggregator.ts frontend/src/lib/holdings/__tests__/aggregator.test.ts frontend/src/components/stocks/StockTable.tsx
git commit -m "feat(stocks): StockTable + aggregator integrate indicators + leader sort + hover K 线"
```

---

## Task 16: StocksPage 集成 + 端到端验证

**Files:**
- Modify: `frontend/src/pages/StocksPage.tsx`
- Modify: `frontend/src/pages/__tests__/StocksPage.test.tsx`

- [ ] **Step 1: 读取现有 StocksPage 与测试**

```bash
cat /Users/dreambt/sources/etf-radar/frontend/src/pages/StocksPage.tsx
```
（先了解现有结构，确认 props / hooks 用法。）

- [ ] **Step 2: 扩展 StocksPage 测试**

打开 `frontend/src/pages/__tests__/StocksPage.test.tsx`，在 fetchSpy 的 mockImplementation 内增加对 `holdings_indicators.json` 的响应分支（在原有 stocks_spot.json 分支之后追加）：

```typescript
if (url.includes('holdings_indicators.json')) {
  return Promise.resolve(new Response(JSON.stringify({
    schema_version: '1.0', generated_at: '...',
    stocks: { '002129': { name: 'TCL中环', strength_60d: 87, strength_20d: 91,
                          rsi_14: 62.3, vol_ratio: 1.85, leader: '⭐⭐' } },
  })));
}
```

并新增一个测试块：

```typescript
it('renders indicators columns and structure summary when present', async () => {
  mockThemes = [
    { id: 'semi', name: '半导体', us_etfs: ['SOXX'], primary_us: 'SOXX',
      primary_cn: '512480', tags: [], note: '', returns: {} as unknown,
      strength: {} as unknown, us_strength: null, cn_strength: null,
      rank: {} as unknown } as unknown as Theme,
  ];
  fetchSpy.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('512480.json') && url.includes('holdings/')) {
      return Promise.resolve(new Response(JSON.stringify({
        etf_code: '512480', etf_name: '半导体ETF',
        disclosure_date: '2026-03-31', fetched_at: '2026-06-23T00:00:00+00:00',
        top_holdings: [{ code: '002129', name: 'TCL中环', weight: 8.5 }],
      })));
    }
    if (url.includes('stocks_spot.json')) {
      return Promise.resolve(new Response(JSON.stringify({
        schema_version: '1.0', generated_at: '...',
        stocks: { '002129': { name: 'TCL中环', close: 12.5, r_1d: 0.025 } },
      })));
    }
    if (url.includes('holdings_indicators.json')) {
      return Promise.resolve(new Response(JSON.stringify({
        schema_version: '1.0', generated_at: '...',
        stocks: { '002129': { name: 'TCL中环', strength_60d: 87, strength_20d: 91,
                              rsi_14: 62.3, vol_ratio: 1.85, leader: '⭐⭐' } },
      })));
    }
    return Promise.resolve(new Response('', { status: 404 }));
  });
  renderAt('/theme/semi/stocks');
  await waitFor(() => expect(screen.getByText('TCL中环')).toBeInTheDocument());
  expect(screen.getByText('87')).toBeInTheDocument();   // strength_60d 徽章值
  expect(screen.getByText('62.3')).toBeInTheDocument(); // RSI 值
  expect(screen.getByText('⭐⭐')).toBeInTheDocument(); // leader 列
  expect(screen.getByLabelText('主题结构摘要')).toBeInTheDocument();
});
```

- [ ] **Step 3: 修改 StocksPage.tsx**

打开 `frontend/src/pages/StocksPage.tsx`，按以下原则修改：

1. 顶部导入 `useStockIndicators` 与 `ThemeStructureSummary`：
```typescript
import { useStockIndicators } from '@/lib/holdings/useStockIndicators';
import { ThemeStructureSummary } from '@/components/stocks/ThemeStructureSummary';
```

2. 在 component body 中加 hook 调用：
```typescript
const { data: indicators } = useStockIndicators();
```

3. 把 `aggregateHoldings(snapshots, spotMap)` 改为 `aggregateHoldings(snapshots, spotMap, indicators)`

4. 在 `<StockTable stocks={aggregated} />` 上方插入：
```tsx
<ThemeStructureSummary stocks={aggregated} />
```

- [ ] **Step 4: 跑 StocksPage 测试**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/pages/__tests__/StocksPage 2>&1 | grep -E "(Test Files|Tests|FAIL|✓|×)" | tail -10
```
Expected: 全部 PASS（原 3 个 + 新 1 个 = 4 PASS）

- [ ] **Step 5: 跑全部 frontend 测试**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | grep -E "(Test Files|Tests|FAIL)" | tail -10
```
Expected: 全部 PASS

- [ ] **Step 6: 跑 lint + typecheck**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx eslint src 2>&1 | tail -10
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -10
```
Expected: 0 errors

- [ ] **Step 7: 提交**

```bash
git add frontend/src/pages/StocksPage.tsx frontend/src/pages/__tests__/StocksPage.test.tsx
git commit -m "feat(stocks): StocksPage integrates indicators hook + structure summary"
```

---

## Task 17: 端到端 smoke + 上线 Checklist

**Files:**
- 无新增文件，纯验证 + 触发首次 backfill

- [ ] **Step 1: 跑后端全部测试 + 前端全部测试**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -5
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | grep -E "(Test Files|Tests)" | tail -5
```
Expected: 全部 PASS

- [ ] **Step 2: 本地 dryrun backfill（小样本）**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run python -c "
from src.stocks_history_pipeline import run_history_backfill
from src.providers.stock_history_provider import StockHistoryProvider
from unittest.mock import patch
from pathlib import Path

with patch('src.stocks_history_pipeline._fetch_universe', return_value=['002129']):
    run_history_backfill(Path('../data/holdings'), Path('/tmp/stocks-smoke'),
                          days=30, max_workers=2)
print('OK')
ls /tmp/stocks-smoke/
"
```
Expected: 写出 close_series.json / volume_series.json / ohlc/002129.json / index.json

- [ ] **Step 3: 本地 dryrun daily（用 smoke 产物）**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run python -c "
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from src.stocks_daily_pipeline import run_daily_pipeline

fake_spot = pd.DataFrame({'代码': ['002129'], '名称': ['TCL'], '最新价': [13.0], '成交量': [3000000]})
with patch('src.stocks_daily_pipeline._fetch_today_spot', return_value=fake_spot):
    run_daily_pipeline(Path('../data/holdings'), Path('/tmp/stocks-smoke'), today=date(2026, 6, 25))
print(json.loads(open('/tmp/stocks-smoke/holdings_indicators.json').read())['stocks'])
"
```
Expected: holdings_indicators.json 内含 002129 的 indicators

- [ ] **Step 4: 推送所有 commit 到 main（用户确认后）**

**注意：本步骤需要用户显式授权才能执行**。Plan 执行者应停下并询问用户后再 push。

- [ ] **Step 5: 手动触发 backfill workflow（用户确认后）**

```bash
gh workflow run stocks-history-backfill.yml -f days=75 -f max_workers=4
gh run watch
```
Expected: 完成 + commit `data: stocks history backfill ...`

- [ ] **Step 6: 等待 BJT 16:30 自然 cron 或手动触发 daily**

```bash
gh workflow run stocks-daily.yml
gh run watch
```
Expected: 完成 + commit + 触发 deploy-frontend

- [ ] **Step 7: 线上验证（用户在浏览器中确认）**

打开 `/theme/{any}/stocks` 页面：
- [ ] 新 4 列（60d / 20d / RSI / 量比）渲染
- [ ] 龙头列显示 ⭐ 标签且龙头自动顶到表头
- [ ] hover 行显示 60 日 K 线小图
- [ ] 主题结构摘要在表格上方显示
- [ ] 移动端无 K 线浮层（仅桌面端 md+）

- [ ] **Step 8: 更新观测记录（用户授权后）**

通过 `mcp__plugin_claude-mem_mcp-search__observation_add` 记录上线事实。

---

## Self-Review 校对

**Spec 覆盖检查：**
- §1 目标场景 → Task 4 (leader) + Task 14 (structure summary) + Task 10 (structureInsight)
- §3 数据契约 → Task 1 (models + schemas) + Task 6 (history pipeline) + Task 7 (daily pipeline)
- §3.3 holdings_indicators → Task 7
- §3.4 ohlc/{code}.json → Task 6
- §4.2 batch_strength_per_dim → Task 2
- §4.3 stock_indicators → Task 3
- §4.4 leader_rule → Task 4
- §4.5 history_pipeline → Task 6
- §4.6 daily_pipeline → Task 7
- §4.7 stock_history_provider → Task 5
- §5 前端 UI → Task 9-16
- §5.5 indicatorThresholds → Task 9
- §5.6 aggregator 扩展 → Task 15
- §6.1 CI workflows → Task 8
- §6.2 测试策略 → 每个 Task 内 TDD
- §6.3 风险表 → 不需单独任务（已在 §4.5 / §6.1 等任务中落实）
- §6.4 Checklist → Task 17

**类型一致性：**
- LeaderStar 在 stockIndicators.ts 定义，leaderRank.ts / structureInsight 测试中使用统一类型 ✅
- StockIndicators 字段 `strength_60d` (int | None) 在 backend (Optional[int]) / frontend (number | null) 对齐 ✅
- `compareLeader(b, a)` 在 StockTable 与测试中用法一致（降序）✅
- `_fetch_universe` / `_fetch_today_spot` 在 pipeline 测试中 patch 路径一致 ✅

**Placeholder 扫描：**
- 全部步骤都附完整代码或具体命令 ✅
- 仅 Task 17 Step 4/5 标注「需用户授权」是因为属于 push / workflow trigger 的高风险动作（符合 CLAUDE.md 规则）

---

## 执行选项

Plan 已写入 `docs/superpowers/plans/2026-06-25-theme-stocks-phase-2.md`（17 个 Task）。
