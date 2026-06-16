# Snapshots Backfill 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 写一个一次性回填脚本，从历史 OHLC 数据回算过去 ~120 个交易日的 `data/snapshots/<date>/{themes,signals,etfs,meta}.json`，并生成 `data/latest/snapshots-index.json`。绕过 spec 中"等数据自然积累 4 周"的路径依赖假设，让 Phase B 时间轴回放立即具备数据基础。

**Architecture:**

核心发现（已验证）：**所有 scoring 函数（`_log_return` / `_ytd_return` / `mapping_score` / `signal_for_*`）已天然 as-of-friendly** —— 它们以传入 DataFrame 的最后一行为锚点计算。这意味着回填不需要改动任何计算函数，只需：

1. **重构 `pipeline.run_pipeline`**，把"业务计算 + JSON 构造"（当前 step 1-9，约 200 行）提取成纯函数 `compute_outputs(themes, us_ohlc, cn_ohlc, algo, asof_bjt, mode, intraday) -> tuple[dict, dict, dict, dict]`。`run_pipeline` 重构后只负责数据拉取 + 调用 `compute_outputs` + 落盘。**行为零变化**（现有 smoke 测试持续通过）。
2. **新增 `backfill_snapshots.py` 主脚本**：一次性拉所有 symbol 的足够长历史 → 遍历 BJT 工作日 D → 在内存里 `df[df['date'].dt.date <= D]` 切片 → 调用 `compute_outputs(..., asof_bjt=D)` → 写 `data/snapshots/<D>/*.json`。
3. **`snapshots-index.py` 模块**：扫 `data/snapshots/` 输出 `data/latest/snapshots-index.json`（spec §4.1 定义的 schema）。脚本末尾自动生成。

**Tech Stack:** Python 3.11 + pandas + pydantic（沿用现有），新增 `tqdm`（进度条）。

---

## 文件结构

| 文件 | 操作 | 责任 |
|---|---|---|
| `backend/src/pipeline.py` | 重构 | 把 step 1-9 提取为 `compute_outputs()` 纯函数；`run_pipeline` 调用它 |
| `backend/src/output/snapshots_index.py` | 创建 | `build_snapshots_index()` + `write_snapshots_index()` |
| `backend/scripts/__init__.py` | 创建 | 空文件，让 scripts 成为 package |
| `backend/scripts/backfill_snapshots.py` | 创建 | CLI 脚本：参数化拉数据 + 切片循环 + 写 snapshots + 写 index |
| `backend/tests/test_pipeline_compute_outputs.py` | 创建 | `compute_outputs()` as-of 单元测试 |
| `backend/tests/test_snapshots_index.py` | 创建 | `snapshots_index` 模块单元测试 |
| `backend/tests/scripts/__init__.py` | 创建 | 空文件 |
| `backend/tests/scripts/test_backfill_snapshots.py` | 创建 | 端到端 fixture 测试 |
| `backend/pyproject.toml` | 修改 | 添加 `tqdm` 到 dependencies |
| `data/snapshots/<dates>/` | 运行产出 | ~120 天 backfilled snapshots |
| `data/latest/snapshots-index.json` | 运行产出 | snapshots 索引 |
| `README.md` | 修改 | 新增 "数据归档与回填" section |

---

## Task 1: 重构 `compute_outputs()` 纯函数提取

**Files:**
- Modify: `backend/src/pipeline.py:153-389`（`run_pipeline` 内部 step 1-9 提取）

**目标：** 把 `run_pipeline` 中"业务计算 + JSON 构造"提取成纯函数，行为零变化。

### 重构后接口

```python
def compute_outputs(
    themes: list[ThemeConfig],
    us_ohlc: dict[str, pd.DataFrame],
    cn_ohlc: dict[str, pd.DataFrame],
    us_failed: list[str],
    cn_failed: list[str],
    algo: AlgoConfig,
    asof_bjt: datetime,           # 用于 generated_at + calendar 字段
    mode: PipelineMode,            # 用于 last_intraday_refresh 字段
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """从已采集的 OHLC 数据计算并构造 4 个输出 JSON（themes/etfs/signals/meta）。

    asof_bjt 是 as-of 锚定时间（BJT, 带时区）。所有 calendar 字段、generated_at
    均基于此时间。pipeline.run_pipeline 调用时传 datetime.now(tz=BJT)，
    backfill 脚本调用时传该 D 当晚 16:00 BJT。

    返回顺序: (themes_json, etfs_json, signals_json, meta_json)
    """
```

### 重构步骤

`run_pipeline` 原 step 1-9 全部移入 `compute_outputs`。`run_pipeline` 剩下：

```python
def run_pipeline(mode, data_root, config_dir):
    log.info(f'pipeline start mode={mode}')
    themes = load_themes(config_dir / 'themes.yml')
    algo = load_algo_config(config_dir / 'algo.yml')
    yf_provider = YfinanceProvider()
    ak_provider = AkshareProvider()
    us_ohlc, us_failed = _collect_us_ohlc(themes, yf_provider)
    cn_ohlc, cn_failed = _collect_cn_ohlc(themes, ak_provider)

    now_utc = datetime.now(timezone.utc)
    now_bjt = now_utc.astimezone(BJT)
    themes_json, etfs_json, signals_json, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, us_failed, cn_failed, algo,
        asof_bjt=now_bjt, mode=mode,
    )

    atomic_write_json(data_root / 'latest' / 'themes.json', themes_json)
    atomic_write_json(data_root / 'latest' / 'etfs.json', etfs_json)
    atomic_write_json(data_root / 'latest' / 'signals.json', signals_json)
    atomic_write_json(data_root / 'latest' / 'meta.json', meta_json)
    log.info(f'pipeline done, failed={len(us_failed) + len(cn_failed)}')
```

`compute_outputs` 内部基于 `asof_bjt` 构造 `today_bjt = asof_bjt.date()`、`generated_at = asof_bjt.isoformat()`。`now_utc` 用于 `is_us_session_active(asof_bjt.astimezone(timezone.utc))`。

**关键细节：**
- `compute_outputs` 中 `stale_minutes=0`、`last_intraday_refresh` 逻辑保持原样
- `meta_json` 添加新字段 `backfilled: bool`，默认 False，回填脚本调用时传 True（用 kwarg 区分）
- 接口签名添加 `backfilled: bool = False` 参数

### TDD 步骤

- [ ] **Step 1: 跑现有 smoke 测试确认基线**

```bash
cd backend && pytest tests/test_pipeline_smoke.py -v
```

Expected: 2 tests pass.

- [ ] **Step 2: 实施重构，将 `compute_outputs` 提取出来**

具体改动：
1. 在 `pipeline.py` 顶部 imports 后定义新函数 `compute_outputs(themes, us_ohlc, cn_ohlc, us_failed, cn_failed, algo, asof_bjt, mode, backfilled=False)`
2. 将原 `run_pipeline` 第 168-388 行的 step 1-9 全部移入 `compute_outputs`，并将原本的 `today_bjt`/`now_bjt`/`now_utc` 引用全部替换为基于 `asof_bjt` 计算的版本
3. `meta` 构造时添加 `backfilled` 字段（需先在 `models.MetaInfo` pydantic 模型加 `backfilled: bool = False` 字段）
4. 返回 `(themes_json, etfs_json, signals_json, meta_json)`
5. `run_pipeline` 改为上面"重构步骤"代码块所示

- [ ] **Step 3: 验证 smoke 测试仍通过**

```bash
cd backend && pytest tests/test_pipeline_smoke.py -v
```

Expected: 2 tests pass.

如果失败：检查 (a) `MetaInfo.backfilled` 是否添加、(b) `asof_bjt` 与原 `now_bjt` 行为是否一致。

- [ ] **Step 4: 跑全量后端测试**

```bash
cd backend && pytest -v
```

Expected: 所有原有测试 pass。

- [ ] **Step 5: Commit**

```bash
git add backend/src/pipeline.py backend/src/models.py docs/superpowers/plans/2026-06-16-snapshots-backfill.md
git commit -m "refactor(pipeline): extract compute_outputs pure function for backfill"
```

---

## Task 2: `compute_outputs()` as-of 单元测试（含跨年 YTD）

**Files:**
- Create: `backend/tests/test_pipeline_compute_outputs.py`

**目标：** 验证 `compute_outputs(asof_bjt=D)` 在不同 D 下产出的 `returns.r_*` / `r_ytd` / calendar 字段正确。

### TDD 步骤

- [ ] **Step 1: 写失败测试**

```python
"""compute_outputs() as-of 行为单测"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd  # type: ignore[import-untyped]
import pytest

from src.config_loader import load_algo_config, load_themes
from src.pipeline import PipelineMode, compute_outputs

BJT = ZoneInfo('Asia/Shanghai')


def _make_ohlc(start: str, n: int, base: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.date_range(start, periods=n, tz='UTC'),
        'open': [base] * n, 'high': [base * 1.01] * n, 'low': [base * 0.99] * n,
        'close': [base + i * step for i in range(n)],
        'volume': [10000] * n, 'amount': [base * 10000.0] * n,
    })


@pytest.fixture
def config():
    config_dir = Path(__file__).parent.parent.parent / 'config'
    themes = load_themes(config_dir / 'themes.yml')
    algo = load_algo_config(config_dir / 'algo.yml')
    return themes, algo


def test_compute_outputs_asof_date_reflects_in_generated_at(config):
    themes, algo = config
    us_ohlc = {sym: _make_ohlc('2025-01-01', 200) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-01-01', 200) for t in themes for cn in t.cn_etfs}
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    themes_json, _, _, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    assert themes_json['generated_at'].startswith('2026-04-15T16:00')
    # calendar.cn_trading_today 应基于 asof 日期 (2026-04-15 是周三, 工作日)
    assert meta_json['calendar']['cn_trading_today'] is True


def test_compute_outputs_returns_reflect_asof_truncation(config):
    """切片到 D 日的 close, r_1d 应等于 ln(close[D]/close[D-1])"""
    themes, algo = config
    import math
    # 200 天数据, 我们切到第 100 天 D
    us_ohlc = {sym: _make_ohlc('2025-01-01', 200) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-01-01', 200) for t in themes for cn in t.cn_etfs}

    # 切片到第 100 天 (index 99)
    D_idx = 99
    sliced_us = {k: v.iloc[:D_idx + 1].copy() for k, v in us_ohlc.items()}
    sliced_cn = {k: v.iloc[:D_idx + 1].copy() for k, v in cn_ohlc.items()}
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    themes_json, _, _, _ = compute_outputs(
        themes, sliced_us, sliced_cn, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    # base=100, step=0.5, r_1d = ln(close[99]/close[98]) = ln(149.5/149.0)
    expected_r1d = math.log(149.5 / 149.0)
    actual = themes_json['themes'][0]['returns']['r_1d']
    assert abs(actual - expected_r1d) < 1e-6


def test_compute_outputs_ytd_crosses_year_boundary(config):
    """asof 2026-01-15 时, r_ytd 应基于 2026-01-02 起点, 不应回退到 2025"""
    themes, algo = config
    import math
    # 数据从 2025-10-01 到 2026-01-20, 包含跨年
    n = (datetime(2026, 1, 20) - datetime(2025, 10, 1)).days + 1
    us_ohlc = {sym: _make_ohlc('2025-10-01', n) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-10-01', n) for t in themes for cn in t.cn_etfs}

    # 切到 2026-01-15 (index = (2026-01-15 - 2025-10-01).days)
    D_idx = (datetime(2026, 1, 15) - datetime(2025, 10, 1)).days
    sliced_us = {k: v.iloc[:D_idx + 1].copy() for k, v in us_ohlc.items()}
    sliced_cn = {k: v.iloc[:D_idx + 1].copy() for k, v in cn_ohlc.items()}
    asof = datetime(2026, 1, 15, 16, 0, tzinfo=BJT)

    themes_json, _, _, _ = compute_outputs(
        themes, sliced_us, sliced_cn, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    # r_ytd 应基于 2026-01-01 (or 第一个 2026 数据点) 到 2026-01-15
    # _ytd_return 用 df.iloc[-1]['date'].year 推断, 取 same_year 第一个
    # 数据 2026 部分: 2026-01-01 to 2026-01-15, 16 个点, start=close[当年第一个], end=close[15]
    actual = themes_json['themes'][0]['returns']['r_ytd']
    # 跨年验证: r_ytd 应该是正数 (close 单调递增), 且不应是 ln(close[D]/close[2025-10-01])
    assert actual is not None
    assert actual > 0
    # 进一步断言: 当年起点 close vs 跨 2025 起点 close 差距明显
    # 跨 2025 起点 ln 应该 > r_ytd, 因为序列单调递增, 起点越早值越大
    full_span_return = math.log(sliced_us[next(iter(sliced_us))]['close'].iloc[-1]
                                / sliced_us[next(iter(sliced_us))]['close'].iloc[0])
    assert actual < full_span_return  # r_ytd 不应回退到 2025


def test_compute_outputs_backfilled_flag_propagates(config):
    themes, algo = config
    us_ohlc = {sym: _make_ohlc('2025-01-01', 200) for t in themes for sym in t.us_etfs}
    cn_ohlc = {cn.code: _make_ohlc('2025-01-01', 200) for t in themes for cn in t.cn_etfs}
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    _, _, _, meta_default = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )
    _, _, _, meta_backfilled = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof_bjt=asof, mode=PipelineMode.FULL,
        backfilled=True,
    )

    assert meta_default['backfilled'] is False
    assert meta_backfilled['backfilled'] is True


def test_compute_outputs_handles_empty_cache(config):
    """全部 symbol 数据为空 — 不应崩溃, returns 全 None, strength 全 0"""
    themes, algo = config
    asof = datetime(2026, 4, 15, 16, 0, tzinfo=BJT)

    themes_json, etfs_json, signals_json, meta_json = compute_outputs(
        themes, {}, {}, list({sym for t in themes for sym in t.us_etfs}),
        list({cn.code for t in themes for cn in t.cn_etfs}),
        algo, asof_bjt=asof, mode=PipelineMode.FULL,
    )

    assert themes_json['themes'][0]['returns']['r_1d'] is None
    assert themes_json['themes'][0]['strength']['composite'] == 0
    assert meta_json['providers']['us']['status'] == 'degraded'
```

- [ ] **Step 2: 运行测试，确认通过**

```bash
cd backend && pytest tests/test_pipeline_compute_outputs.py -v
```

Expected: 5 tests pass.

如果失败：根据具体失败定位 `compute_outputs` 中 `asof_bjt` 处理位置。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_pipeline_compute_outputs.py
git commit -m "test(pipeline): as-of unit tests for compute_outputs incl YTD boundary"
```

---

## Task 3: `snapshots_index` 模块

**Files:**
- Create: `backend/src/output/snapshots_index.py`
- Create: `backend/tests/test_snapshots_index.py`

**目标：** 扫 `data/snapshots/` 输出 `data/latest/snapshots-index.json`。

### Schema（基于 spec §4.1）

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-16T13:00:00+08:00",
  "snapshots": [
    {"date": "2026-06-15", "themes_path": "snapshots/2026-06-15/themes.json"},
    {"date": "2026-06-16", "themes_path": "snapshots/2026-06-16/themes.json"}
  ]
}
```

### TDD 步骤

- [ ] **Step 1: 写失败测试**

```python
"""snapshots_index 模块单测"""
import json
import tempfile
from pathlib import Path

from src.output.snapshots_index import build_snapshots_index, write_snapshots_index


def _touch_snapshot(snap_root: Path, date_str: str) -> None:
    d = snap_root / date_str
    d.mkdir(parents=True, exist_ok=True)
    (d / 'themes.json').write_text('{}', encoding='utf-8')


def test_build_index_returns_sorted_dates():
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        snap_root = data_root / 'snapshots'
        _touch_snapshot(snap_root, '2026-06-15')
        _touch_snapshot(snap_root, '2026-04-01')
        _touch_snapshot(snap_root, '2026-05-10')

        idx = build_snapshots_index(data_root)

        assert idx['schema_version'] == '1.0'
        assert 'generated_at' in idx
        dates = [s['date'] for s in idx['snapshots']]
        assert dates == ['2026-04-01', '2026-05-10', '2026-06-15']
        # themes_path 是相对 data_root 的相对路径 (POSIX 风格)
        assert idx['snapshots'][0]['themes_path'] == 'snapshots/2026-04-01/themes.json'


def test_build_index_skips_invalid_dirs():
    """非日期格式的目录 / 缺 themes.json 的目录 应被跳过"""
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        snap_root = data_root / 'snapshots'
        _touch_snapshot(snap_root, '2026-06-15')
        # 无 themes.json 的目录
        (snap_root / '2026-06-16').mkdir(parents=True)
        # 非日期格式的目录
        (snap_root / 'not-a-date').mkdir(parents=True)
        (snap_root / 'not-a-date' / 'themes.json').write_text('{}', encoding='utf-8')

        idx = build_snapshots_index(data_root)
        dates = [s['date'] for s in idx['snapshots']]
        assert dates == ['2026-06-15']


def test_build_index_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        (data_root / 'snapshots').mkdir(parents=True)
        idx = build_snapshots_index(data_root)
        assert idx['snapshots'] == []


def test_build_index_missing_snapshots_dir():
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        idx = build_snapshots_index(data_root)
        assert idx['snapshots'] == []


def test_write_snapshots_index_writes_file():
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        snap_root = data_root / 'snapshots'
        _touch_snapshot(snap_root, '2026-06-15')

        write_snapshots_index(data_root)

        path = data_root / 'latest' / 'snapshots-index.json'
        assert path.exists()
        idx = json.loads(path.read_text(encoding='utf-8'))
        assert idx['snapshots'][0]['date'] == '2026-06-15'
```

- [ ] **Step 2: 实施 `snapshots_index.py`**

```python
"""扫 data/snapshots/ 生成 latest/snapshots-index.json"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .writer import atomic_write_json

BJT = ZoneInfo('Asia/Shanghai')
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def build_snapshots_index(data_root: Path) -> dict[str, Any]:
    """扫 data_root/snapshots/<YYYY-MM-DD>/ 目录, 返回索引 dict.

    只收录目录名匹配 YYYY-MM-DD 且包含 themes.json 的快照。
    """
    snap_root = data_root / 'snapshots'
    snapshots: list[dict[str, str]] = []
    if snap_root.exists():
        for d in sorted(snap_root.iterdir()):
            if not d.is_dir():
                continue
            if not _DATE_RE.match(d.name):
                continue
            if not (d / 'themes.json').exists():
                continue
            snapshots.append({
                'date': d.name,
                'themes_path': f'snapshots/{d.name}/themes.json',
            })

    return {
        'schema_version': '1.0',
        'generated_at': datetime.now(timezone.utc).astimezone(BJT).isoformat(),
        'snapshots': snapshots,
    }


def write_snapshots_index(data_root: Path) -> Path:
    idx = build_snapshots_index(data_root)
    out = data_root / 'latest' / 'snapshots-index.json'
    atomic_write_json(out, idx)
    return out
```

- [ ] **Step 3: 跑测试，确认通过**

```bash
cd backend && pytest tests/test_snapshots_index.py -v
```

Expected: 5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/src/output/snapshots_index.py backend/tests/test_snapshots_index.py
git commit -m "feat(output): add snapshots_index module for Phase B"
```

---

## Task 4: `backfill_snapshots.py` 主脚本

**Files:**
- Create: `backend/scripts/__init__.py` (空)
- Create: `backend/scripts/backfill_snapshots.py`
- Modify: `backend/pyproject.toml` (添加 tqdm)

**目标：** CLI 脚本一次拉所有 symbol 历史 → 遍历工作日切片 → 落盘 snapshots → 生成 index。

### 关键算法

```python
# 1. lookback 自动算 (覆盖 r_120d 窗口 + buffer)
days_in_window = (today - start).days
lookback_days = days_in_window + 200

# 2. 一次拉所有 symbol
us_cache = {sym: yf.fetch_ohlc(sym, lookback_days) for sym in us_symbols}
cn_cache = {code: ak.fetch_ohlc(code, lookback_days) for code in cn_codes}

# 3. 遍历工作日 D (BJT)
for D in pd.date_range(start, end, freq='D'):
    if not is_cn_trading_day(D.date()) and not is_us_trading_day(D.date()):
        continue
    skip_if_exists(data_root, D)

    # 切片到 D 当晚 (BJT 16:00 锚定)
    us_sliced = {sym: df[df['date'].dt.date <= D.date()] for sym, df in us_cache.items()}
    cn_sliced = {code: df[df['date'].dt.date <= D.date()] for code, df in cn_cache.items()}

    asof = datetime.combine(D.date(), time(16, 0), tzinfo=BJT)
    themes_json, etfs_json, signals_json, meta_json = compute_outputs(
        themes, us_sliced, cn_sliced, [], [], algo,
        asof_bjt=asof, mode=PipelineMode.FULL, backfilled=True,
    )

    snap_dir = data_root / 'snapshots' / D.strftime('%Y-%m-%d')
    atomic_write_json(snap_dir / 'themes.json', themes_json)
    # ... etfs, signals, meta

# 4. 生成 index
write_snapshots_index(data_root)
```

### CLI 接口

```
python -m scripts.backfill_snapshots \
  --start 2026-01-02 --end 2026-06-13 \
  --data-root data --config-dir config \
  [--skip-existing] [--force] [--no-index] [--lookback N]
```

### TDD 步骤

- [ ] **Step 1: 修改 `pyproject.toml` 添加 tqdm**

在 `backend/pyproject.toml` 的 `[project] dependencies` 列表添加 `"tqdm>=4.66"`，然后 `cd backend && pip install -e .` 安装。

- [ ] **Step 2: 创建 `backend/scripts/__init__.py`**

```python
# Empty - makes scripts a package
```

- [ ] **Step 3: 写脚本（无测试先，测试在 Task 5）**

```python
"""Snapshots 回填脚本

用法:
    python -m scripts.backfill_snapshots --start 2026-01-02 --end 2026-06-13

设计:
    1. 一次拉所有 symbol 的足够长历史 (lookback = days_in_window + 200)
    2. 遍历 [start, end] 工作日 D, 内存切片 cache 到 <= D
    3. 调用 compute_outputs(asof_bjt=D 当晚 16:00 BJT) 计算
    4. 写 data/snapshots/<D>/{themes,signals,etfs,meta}.json
    5. 末尾生成 latest/snapshots-index.json

关键事实:
    - 所有 scoring 函数已 as-of-friendly, 零改动
    - lookback 包括 buffer 是为了覆盖 r_120d 窗口 + r_ytd 跨年起点
    - meta.json 标记 backfilled=true 区分真实归档
"""
from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd  # type: ignore[import-untyped]
from tqdm import tqdm  # type: ignore[import-not-found]

from src.config_loader import load_algo_config, load_themes
from src.etl.calendar import BJT, is_cn_trading_day, is_us_trading_day
from src.output.snapshots_index import write_snapshots_index
from src.output.writer import atomic_write_json
from src.pipeline import PipelineMode, compute_outputs
from src.providers.akshare_provider import AkshareProvider
from src.providers.base import EmptyDataError, EtfDataProvider, ProviderError
from src.providers.yfinance_provider import YfinanceProvider

log = logging.getLogger(__name__)


def _collect_history(
    symbols: list[str], provider: EtfDataProvider, lookback_days: int,
    label: str, jitter_range: tuple[float, float] = (0.0, 0.0),
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """一次性拉所有 symbol 的历史, jitter 仅在 CN provider 用 (yfinance 不需要)。"""
    cache: dict[str, pd.DataFrame] = {}
    failed: list[str] = []
    for sym in tqdm(symbols, desc=f'fetch {label}', unit='sym'):
        try:
            cache[sym] = provider.fetch_ohlc(sym, lookback_days=lookback_days)
        except (ProviderError, EmptyDataError) as e:
            log.warning(f'{label} fetch failed {sym}: {e}')
            failed.append(sym)
        if jitter_range[1] > 0:
            time.sleep(random.uniform(*jitter_range))
    return cache, failed


def _slice_to_date(cache: dict[str, pd.DataFrame], D: date) -> dict[str, pd.DataFrame]:
    """内存切片: 每个 df 截到 date <= D"""
    out: dict[str, pd.DataFrame] = {}
    for sym, df in cache.items():
        sliced = df[df['date'].dt.date <= D]
        if not sliced.empty:
            out[sym] = sliced
    return out


def _iter_trading_days(start: date, end: date) -> list[date]:
    """生成 [start, end] 范围内的 BJT 工作日 (CN 或 US 任一开市)。"""
    out: list[date] = []
    d = start
    while d <= end:
        if is_cn_trading_day(d) or is_us_trading_day(d):
            out.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    return out


def backfill(
    start: date, end: date, data_root: Path, config_dir: Path,
    lookback_days: int | None = None,
    skip_existing: bool = True, force: bool = False, write_index: bool = True,
) -> None:
    if force and skip_existing:
        raise ValueError('--force and --skip-existing are mutually exclusive')

    themes = load_themes(config_dir / 'themes.yml')
    algo = load_algo_config(config_dir / 'algo.yml')

    today = datetime.now(tz=BJT).date()
    if lookback_days is None:
        # (today - start) days + 200 buffer (覆盖 r_120d + r_ytd 跨年起点)
        lookback_days = (today - start).days + 200
    log.info(f'lookback_days={lookback_days}')

    us_symbols = sorted({sym for t in themes for sym in t.us_etfs})
    cn_codes = sorted({cn.code for t in themes for cn in t.cn_etfs})

    log.info(f'fetching {len(us_symbols)} US symbols')
    us_cache, us_failed_init = _collect_history(
        us_symbols, YfinanceProvider(), lookback_days, 'US',
    )
    log.info(f'fetching {len(cn_codes)} CN codes (with jitter)')
    cn_cache, cn_failed_init = _collect_history(
        cn_codes, AkshareProvider(), lookback_days, 'CN', jitter_range=(0.3, 1.0),
    )
    log.info(f'US fetched={len(us_cache)}, failed={len(us_failed_init)}')
    log.info(f'CN fetched={len(cn_cache)}, failed={len(cn_failed_init)}')

    trading_days = _iter_trading_days(start, end)
    log.info(f'backfilling {len(trading_days)} trading days [{start} .. {end}]')

    written = 0
    skipped = 0
    for D in tqdm(trading_days, desc='backfill', unit='day'):
        snap_dir = data_root / 'snapshots' / D.strftime('%Y-%m-%d')
        if skip_existing and (snap_dir / 'themes.json').exists():
            skipped += 1
            continue

        us_sliced = _slice_to_date(us_cache, D)
        cn_sliced = _slice_to_date(cn_cache, D)
        us_failed_D = [s for s in us_symbols if s not in us_sliced]
        cn_failed_D = [c for c in cn_codes if c not in cn_sliced]

        asof = datetime.combine(D, dtime(16, 0), tzinfo=BJT)
        themes_json, etfs_json, signals_json, meta_json = compute_outputs(
            themes, us_sliced, cn_sliced, us_failed_D, cn_failed_D, algo,
            asof_bjt=asof, mode=PipelineMode.FULL, backfilled=True,
        )

        atomic_write_json(snap_dir / 'themes.json', themes_json)
        atomic_write_json(snap_dir / 'etfs.json', etfs_json)
        atomic_write_json(snap_dir / 'signals.json', signals_json)
        atomic_write_json(snap_dir / 'meta.json', meta_json)
        written += 1

    log.info(f'backfill done: written={written}, skipped={skipped}')

    if write_index:
        path = write_snapshots_index(data_root)
        log.info(f'snapshots index: {path}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Backfill snapshots from historical OHLC')
    parser.add_argument('--start', type=date.fromisoformat, required=True,
                        help='起始日期 YYYY-MM-DD (含)')
    parser.add_argument('--end', type=date.fromisoformat, required=True,
                        help='结束日期 YYYY-MM-DD (含)')
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--config-dir', type=Path, default=Path('config'))
    parser.add_argument('--lookback', type=int, default=None,
                        help='历史拉取窗口天数 (默认自动算)')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                        help='跳过已存在的 snapshot 目录 (默认 true)')
    parser.add_argument('--force', action='store_true',
                        help='强制覆盖已存在的 snapshot (覆盖 --skip-existing)')
    parser.add_argument('--no-index', action='store_true',
                        help='跳过 snapshots-index.json 生成')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    skip_existing = args.skip_existing and not args.force
    backfill(
        start=args.start, end=args.end,
        data_root=args.data_root, config_dir=args.config_dir,
        lookback_days=args.lookback,
        skip_existing=skip_existing, force=args.force,
        write_index=not args.no_index,
    )


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 确认脚本能加载（语法 + import 正确）**

```bash
cd backend && python -c "from scripts.backfill_snapshots import backfill; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/__init__.py backend/scripts/backfill_snapshots.py backend/pyproject.toml
git commit -m "feat(scripts): backfill_snapshots CLI for Phase B data preparation"
```

---

## Task 5: 端到端 fixture 测试

**Files:**
- Create: `backend/tests/scripts/__init__.py` (空)
- Create: `backend/tests/scripts/test_backfill_snapshots.py`

**目标：** Mock provider，跑回填 3 天，验证 snapshots 输出 + index 文件，schema 通过。

### TDD 步骤

- [ ] **Step 1: 写端到端测试**

```python
"""backfill_snapshots 端到端测试 (mock provider)"""
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd  # type: ignore[import-untyped]

from scripts.backfill_snapshots import backfill


def _make_history(n: int = 300, base: float = 100.0) -> pd.DataFrame:
    """生成从 2025-09-01 起的 n 天 OHLC, 单调递增 close."""
    return pd.DataFrame({
        'date': pd.date_range('2025-09-01', periods=n, tz='UTC'),
        'open': [base] * n, 'high': [base * 1.01] * n, 'low': [base * 0.99] * n,
        'close': [base + i * 0.5 for i in range(n)],
        'volume': [10000] * n, 'amount': [base * 10000.0] * n,
    })


@patch('scripts.backfill_snapshots.AkshareProvider')
@patch('scripts.backfill_snapshots.YfinanceProvider')
def test_backfill_writes_snapshots_and_index(
    mock_yf: MagicMock, mock_ak: MagicMock,
) -> None:
    mock_yf.return_value.fetch_ohlc.return_value = _make_history()
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_history()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'

        # 回填 3 天 (其中至少包含 1 个交易日)
        backfill(
            start=date(2026, 1, 5), end=date(2026, 1, 8),
            data_root=data_root, config_dir=config_dir,
            lookback_days=300, skip_existing=False,
        )

        snap_root = data_root / 'snapshots'
        snapshot_dirs = sorted(d.name for d in snap_root.iterdir() if d.is_dir())
        # 2026-01-05 (周一) 至 2026-01-08 (周四) 都是工作日
        assert len(snapshot_dirs) >= 3

        # 每个 snapshot 含 4 个文件
        for date_str in snapshot_dirs:
            assert (snap_root / date_str / 'themes.json').exists()
            assert (snap_root / date_str / 'signals.json').exists()
            assert (snap_root / date_str / 'etfs.json').exists()
            assert (snap_root / date_str / 'meta.json').exists()

        # meta.json 标记 backfilled
        meta = json.loads((snap_root / snapshot_dirs[0] / 'meta.json').read_text())
        assert meta['backfilled'] is True

        # themes.json 含 14 主题
        themes = json.loads((snap_root / snapshot_dirs[0] / 'themes.json').read_text())
        assert len(themes['themes']) == 14

        # snapshots-index.json 生成且含全部日期
        idx = json.loads((data_root / 'latest' / 'snapshots-index.json').read_text())
        idx_dates = [s['date'] for s in idx['snapshots']]
        assert idx_dates == snapshot_dirs


@patch('scripts.backfill_snapshots.AkshareProvider')
@patch('scripts.backfill_snapshots.YfinanceProvider')
def test_backfill_skip_existing(
    mock_yf: MagicMock, mock_ak: MagicMock,
) -> None:
    mock_yf.return_value.fetch_ohlc.return_value = _make_history()
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_history()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'

        # 第一次回填: 写 2 天
        backfill(
            start=date(2026, 1, 5), end=date(2026, 1, 6),
            data_root=data_root, config_dir=config_dir,
            lookback_days=300, skip_existing=False,
        )
        first_count = sum(1 for _ in (data_root / 'snapshots').iterdir())

        # 写入哨兵字符串到既有 themes.json, 验证 skip_existing 不覆盖
        sentinel_path = data_root / 'snapshots' / '2026-01-05' / 'themes.json'
        sentinel_path.write_text('SENTINEL', encoding='utf-8')

        # 第二次回填, skip_existing=True
        backfill(
            start=date(2026, 1, 5), end=date(2026, 1, 8),
            data_root=data_root, config_dir=config_dir,
            lookback_days=300, skip_existing=True,
        )

        # 已存在的 2026-01-05 不被覆盖
        assert sentinel_path.read_text(encoding='utf-8') == 'SENTINEL'
        # 新增 2026-01-07, 2026-01-08
        new_count = sum(1 for _ in (data_root / 'snapshots').iterdir())
        assert new_count > first_count


@patch('scripts.backfill_snapshots.AkshareProvider')
@patch('scripts.backfill_snapshots.YfinanceProvider')
def test_backfill_output_schemas_valid(
    mock_yf: MagicMock, mock_ak: MagicMock,
) -> None:
    """回填产物应通过现有 JSON schemas 校验"""
    import jsonschema  # type: ignore[import-untyped]

    mock_yf.return_value.fetch_ohlc.return_value = _make_history()
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_history()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        config_dir = Path(__file__).parent.parent.parent.parent / 'config'
        schemas_root = Path(__file__).parent.parent / 'schemas'

        backfill(
            start=date(2026, 1, 5), end=date(2026, 1, 6),
            data_root=data_root, config_dir=config_dir,
            lookback_days=300, skip_existing=False,
        )

        # 检查 themes/signals/etfs/meta 4 个 schema
        for kind in ('themes', 'signals', 'etfs', 'meta'):
            schema = json.loads((schemas_root / f'{kind}.schema.json').read_text())
            for d_dir in (data_root / 'snapshots').iterdir():
                if d_dir.is_dir():
                    data = json.loads((d_dir / f'{kind}.json').read_text())
                    jsonschema.validate(data, schema)
```

- [ ] **Step 2: 跑测试，确认通过**

```bash
cd backend && pytest tests/scripts/ -v
```

Expected: 3 tests pass.

如果失败：
- 如果 schema 不通过 meta，检查 `backfilled` 字段是否需要添加到 `tests/schemas/meta.schema.json`（如果原 schema 严格 `additionalProperties: false`）

- [ ] **Step 3: Commit**

```bash
git add backend/tests/scripts/__init__.py backend/tests/scripts/test_backfill_snapshots.py
git commit -m "test(scripts): end-to-end backfill_snapshots test with schema validation"
```

---

## Task 6: 真实运行 + 文档

**Files:**
- Modify: `README.md`（新增"数据归档与回填"section）
- Run: 真实回填 ~120 个交易日（2026-01-02 ~ 2026-06-13）

### TDD 步骤

- [ ] **Step 1: 检查现有 snapshots，识别真实归档**

```bash
ls data/snapshots/
```

确认 `2026-06-15/` 是真实归档（cn-eod-archive cron 产出），不应被覆盖。`--skip-existing` 默认开启会保护它。

- [ ] **Step 2: Dry-run（小范围验证）**

先回填 5 个工作日验证（仅作真实数据可达性检查）：

```bash
cd backend && python -m scripts.backfill_snapshots \
    --start 2026-06-08 --end 2026-06-13 \
    --data-root ../data --config-dir ../config
```

Expected: 输出日志显示 fetched US/CN symbols + 写入 5 个 snapshot 目录 + 生成 index。

验证：
- `data/snapshots/2026-06-15/themes.json` 仍是原内容（未覆盖）
- 新增 `data/snapshots/2026-06-08/` 等目录
- `data/latest/snapshots-index.json` 含全部日期

- [ ] **Step 3: 全量真实回填**

```bash
cd backend && python -m scripts.backfill_snapshots \
    --start 2026-01-02 --end 2026-06-13 \
    --data-root ../data --config-dir ../config
```

Expected:
- 拉数据阶段 ~10-15 分钟（CN provider jitter）
- 写入阶段 ~1-2 分钟
- 最终 `data/snapshots/` 含约 110-115 个交易日目录

验证：

```bash
ls data/snapshots/ | wc -l    # 应 >= 110
ls data/snapshots/ | head -3   # 起始日期应 ~2026-01-02
ls data/snapshots/ | tail -3   # 末尾应 ~2026-06-15 (含 cron 真实归档)
cat data/latest/snapshots-index.json | head -20
```

如果 US/CN provider 大批量失败，检查日志的 `failed_symbols`，必要时分段重跑。

- [ ] **Step 4: 更新 README.md**

在 README.md 找到 "## 部署" 或 "## 数据" section，新增子 section（贴近现有风格）：

```markdown
### 数据归档与回填

每日 cron (`30 7 * * 1-5`) 自动把 `data/latest/` 归档到 `data/snapshots/<BJT-date>/`，
供 Phase B 时间轴回放使用。

**首次回填（一次性）**: 如果 snapshots 历史不足，运行回填脚本生成历史数据：

\`\`\`bash
cd backend
python -m scripts.backfill_snapshots --start 2026-01-02 --end 2026-06-13
\`\`\`

回填产物的 `meta.json` 含 `backfilled: true` 标记，区分自动归档。
`--skip-existing` 默认开启，保护已归档的真实数据。

回填脚本同时生成 `data/latest/snapshots-index.json`，前端 Phase B 据此发现可用日期。
```

- [ ] **Step 5: 跑全量测试 + 构建（确认 main 路径无回归）**

```bash
cd backend && pytest -v
```

Expected: 所有测试 pass（含新增的 13 个）。

```bash
cd frontend && npx vitest run
```

Expected: 54 tests pass（前端无改动，应不受影响）。

- [ ] **Step 6: Commit**

```bash
git add README.md data/snapshots/ data/latest/snapshots-index.json
git commit -m "data: backfill snapshots 2026-01-02 to 2026-06-13 + README docs"
```

---

## 验收清单

- [ ] `compute_outputs()` 是纯函数，接受 `asof_bjt` 参数，零副作用
- [ ] `run_pipeline` 行为零变化（smoke 测试通过）
- [ ] 5 个 as-of 单测覆盖：日期反映、收益切片、YTD 跨年、backfilled flag、empty cache
- [ ] `snapshots-index.json` 含全部回填日期，按字典序排序
- [ ] 真实回填产出 ≥ 110 个交易日 snapshots
- [ ] meta.json 的 `backfilled` 字段正确区分回填 vs 真实归档
- [ ] 既有 `data/snapshots/2026-06-15/` 真实归档未被覆盖
- [ ] frontend 54 测试 + backend 全量测试通过
- [ ] README.md 含回填说明

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| yfinance 历史拉取限流 | tqdm 进度条 + 失败 symbol 日志，分段可重跑 |
| akshare 大量失败 | jitter 0.3-1.0s + best-effort（单 symbol 失败不中止） |
| `data/snapshots/2026-06-15/` 真实归档被覆盖 | `--skip-existing` 默认开启 |
| meta.json schema 严格不允许 `backfilled` 字段 | 同时更新 `tests/schemas/meta.schema.json` |
| 跨年 YTD 边界 bug | Task 2 显式跨年单测覆盖 |
| `compute_outputs` 重构破坏 run_pipeline | Task 1 跑现有 smoke 测试保底 |
