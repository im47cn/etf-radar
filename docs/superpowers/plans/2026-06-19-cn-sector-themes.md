# A 股独立行业主题融合 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 14 个中美映射主题之外，新增 7 个 A 股独立行业主题（白酒、消费、医疗器械、家电、地产、传媒、红利），融合进主题列表与轮动散点图；散点图支持"美股/A 股"双 strength 模式切换。

**Architecture:** 单一配置文件 `config/themes.yml` 扩展 + 数据模型放宽 (`us_etfs/primary_us` 可空、新增 `primary_cn`) + Pipeline 双 strength 计算 (全主题在 US 池和 CN 池各算一次) + 前端类型扩展 + Rotation Tab 模式切换。

**Tech Stack:** Python 3.11 + Pydantic / pandas / pytest（backend）；TypeScript + React + zod + vitest + playwright（frontend）。

**关联设计文档:** `docs/superpowers/specs/2026-06-19-cn-sector-themes-design.md`

**项目级约定:** 本仓库 CLAUDE.md 要求"若用户没主动要求，不要执行 git 提交"。每个 task 末尾的 commit 步骤需用户授权后再执行；未授权时改为停下汇报本任务的 diff 摘要。

---

## File Structure

```
backend/src/models.py                       修改：ThemeConfig 放宽、ThemeOutput 加 us_strength/cn_strength、TopTheme.primary_us 改 Optional
backend/src/pipeline.py                     修改：us_etfs 空容错、CN 池 strength 计算、themes.json 输出 schema 1.1
backend/src/scoring/signals.py              修改：跳过 primary_us 为 None 的主题
backend/tests/schemas/themes.schema.json    修改：schema 1.1
backend/tests/fixtures/themes_minimal.yml   修改：补 1 个 cn_only 条目
backend/tests/test_config_loader.py         修改：补用例
backend/tests/test_models.py                修改：补用例
backend/tests/test_pipeline_compute_outputs.py  修改：补 cn_only 用例
backend/tests/test_output_schemas.py        修改：schema 1.1 校验
backend/tests/test_signals.py               修改：补 None 用例
config/themes.yml                           修改：追加 7 个 cn_only 主题
frontend/src/types/themes.ts                修改：扩展 ThemeSchema
frontend/src/lib/rotation.ts                修改：themesToRotationPoints 加 mode 参数
frontend/src/lib/__tests__/rotation.test.ts 修改：补 mode 切换用例
frontend/src/components/rotation/ModeToggle.tsx                     新建
frontend/src/components/rotation/__tests__/ModeToggle.test.tsx      新建
frontend/src/components/rotation/RotationScatterWithTrails.tsx      修改：传入 mode
frontend/src/pages/RotationPage.tsx                                  修改：mode 状态 + 计数
frontend/src/components/ThemeList/ThemeRow.tsx                       修改：A 股专属 pill
frontend/src/components/ThemeList/__tests__/ThemeRow.test.tsx        新建
frontend/src/components/ThemeDetail/MappingPanel.tsx                 修改：无映射兜底
frontend/src/components/FilterBar/index.tsx                          修改：仅看 A 股专属 checkbox
frontend/src/__fixtures__/snapshots.ts                               修改：fixture 扩充
```

---

## Task 1: 扩展 ThemeConfig 数据模型

**Files:**
- Modify: `backend/src/models.py:11-25`
- Test: `backend/tests/test_models.py`

放宽 `us_etfs`/`primary_us` 为可选，新增 `primary_cn`，加 `model_validator` 保证"至少一个 primary 非空"且 `primary_us` 若有必须在 `us_etfs` 中。

- [ ] **Step 1.1: 写失败测试**

在 `backend/tests/test_models.py` 追加（如文件不存在则创建并加上必要 import）：

```python
import pytest
from pydantic import ValidationError
from src.models import ThemeConfig, CnEtfConfig


def _cn(code='000001'):
    return CnEtfConfig(code=code, name='测试ETF', tracking='测试指数', match_type='exact')


def test_theme_config_cn_only_minimal():
    """纯 A 股主题：无 us_etfs/primary_us，只需 primary_cn。"""
    t = ThemeConfig(id='cn_x', name='测试', tags=[], primary_cn='000001', cn_etfs=[_cn()])
    assert t.primary_us is None
    assert t.us_etfs == []
    assert t.primary_cn == '000001'


def test_theme_config_requires_at_least_one_primary():
    with pytest.raises(ValidationError, match='primary_us or primary_cn required'):
        ThemeConfig(id='cn_x', name='测试', tags=[], cn_etfs=[_cn()])


def test_theme_config_primary_us_must_be_in_us_etfs():
    with pytest.raises(ValidationError, match='primary_us must be in us_etfs'):
        ThemeConfig(id='m', name='M', us_etfs=['A'], primary_us='B', tags=[], cn_etfs=[_cn()])


def test_theme_config_mapped_backward_compat():
    """现有映射主题加载仍正常。"""
    t = ThemeConfig(id='m', name='M', us_etfs=['SOXX'], primary_us='SOXX',
                    tags=['半导体'], cn_etfs=[_cn()])
    assert t.primary_us == 'SOXX'
    assert t.primary_cn is None
```

- [ ] **Step 1.2: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_models.py -v 2>&1 | tail -20
```

Expected: FAIL with `ValidationError: us_etfs Field required` 或 `primary_us Field required`（因为当前模型这两个字段必填）。

- [ ] **Step 1.3: 修改 ThemeConfig**

编辑 `backend/src/models.py:1-25`，将顶部 import 与 `ThemeConfig` 替换为：

```python
"""Pydantic 模型 — 与 JSON Schema 1:1 对应"""
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

MatchType = Literal['exact', 'wide']
SignalType = Literal['resonance', 'transmission', 'divergence']
ProviderStatus = Literal['ok', 'fallback', 'degraded', 'stale']
DimName = Literal['short', 'mid', 'long']


class CnEtfConfig(BaseModel):
    code: str
    name: str
    tracking: str
    match_type: MatchType


class ThemeConfig(BaseModel):
    id: str
    name: str
    us_etfs: list[str] = Field(default_factory=list)
    primary_us: Optional[str] = None
    primary_cn: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    note: str = ''
    cn_etfs: list[CnEtfConfig]

    @model_validator(mode='after')
    def _validate_primaries(self) -> 'ThemeConfig':
        if not self.primary_us and not self.primary_cn:
            raise ValueError(f"theme {self.id}: primary_us or primary_cn required")
        if self.primary_us and self.primary_us not in self.us_etfs:
            raise ValueError(f"theme {self.id}: primary_us must be in us_etfs")
        return self
```

- [ ] **Step 1.4: 运行测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_models.py -v 2>&1 | tail -20
```

Expected: 4 个新用例全部 PASS；其余既有 test_models.py 用例不受影响。

- [ ] **Step 1.5: 跑全量 backend 测试确保未破坏既有行为**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -10
```

Expected: 全部 PASS（如有原有 ThemeConfig 构造用例缺字段，仍能 backward-compat 通过）。如有失败，回到 1.3 排查（很可能是 `primary_us` 必填断言之前的旧用例，需要补 `primary_cn` 或调整）。

- [ ] **Step 1.6: 等待用户授权后 commit**

```bash
git add backend/src/models.py backend/tests/test_models.py
git commit -m "feat(models): relax ThemeConfig to allow cn_only themes"
```

---

## Task 2: 扩展 ThemeOutput 与 TopTheme 模型

**Files:**
- Modify: `backend/src/models.py:81-91`、`120-124`
- Test: `backend/tests/test_models.py`

ThemeOutput 加 `us_strength` / `cn_strength`（Optional）；`primary_us` 改可选；TopTheme `primary_us` 改 Optional 以兼容纯 A 股主题登顶。

- [ ] **Step 2.1: 写失败测试**

追加到 `backend/tests/test_models.py`：

```python
from src.models import ThemeOutput, TopTheme, Strength, Returns, Rank


def _s(c=50):
    return Strength(short=c, mid=c, long=c, composite=c)


def _rk():
    return Rank(short=1, mid=1, long=1, composite=1)


def test_theme_output_mapped_carries_us_strength():
    t = ThemeOutput(
        id='m', name='M', us_etfs=['SOXX'], primary_us='SOXX',
        primary_cn=None, tags=[], note='',
        returns=Returns(), strength=_s(),
        us_strength=_s(60), cn_strength=_s(40), rank=_rk(),
    )
    assert t.us_strength.composite == 60
    assert t.cn_strength.composite == 40


def test_theme_output_cn_only_has_no_us_strength():
    t = ThemeOutput(
        id='cn_x', name='X', us_etfs=[], primary_us=None,
        primary_cn='000001', tags=[], note='',
        returns=Returns(), strength=_s(40),
        us_strength=None, cn_strength=_s(40), rank=_rk(),
    )
    assert t.us_strength is None
    assert t.cn_strength.composite == 40


def test_top_theme_allows_null_primary_us():
    top = TopTheme(id='cn_x', name='X', primary_us=None, composite_strength=80)
    assert top.primary_us is None
```

- [ ] **Step 2.2: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_models.py::test_theme_output_mapped_carries_us_strength tests/test_models.py::test_theme_output_cn_only_has_no_us_strength tests/test_models.py::test_top_theme_allows_null_primary_us -v 2>&1 | tail -15
```

Expected: FAIL，缺字段或 type error。

- [ ] **Step 2.3: 修改 ThemeOutput 与 TopTheme**

替换 `backend/src/models.py:81-91`（ThemeOutput）：

```python
class ThemeOutput(BaseModel):
    id: str
    name: str
    us_etfs: list[str] = Field(default_factory=list)
    primary_us: Optional[str] = None
    primary_cn: Optional[str] = None
    tags: list[str]
    note: str
    returns: Returns
    strength: Strength
    us_strength: Optional[Strength] = None
    cn_strength: Optional[Strength] = None
    rank: Rank
```

替换 `backend/src/models.py:120-124`（TopTheme）：

```python
class TopTheme(BaseModel):
    id: str
    name: str
    primary_us: Optional[str] = None
    composite_strength: int
```

- [ ] **Step 2.4: 运行测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_models.py -v 2>&1 | tail -15
```

Expected: 所有用例 PASS。

- [ ] **Step 2.5: 等待用户授权后 commit**

```bash
git add backend/src/models.py backend/tests/test_models.py
git commit -m "feat(models): add us_strength/cn_strength to ThemeOutput, allow null primary_us in TopTheme"
```

---

## Task 3: themes.yml 追加 7 个 A 股独立行业

**Files:**
- Modify: `config/themes.yml`（追加到文件末尾）
- Test: `backend/tests/test_config_loader.py`

- [ ] **Step 3.1: 写失败测试**

在 `backend/tests/test_config_loader.py` 追加：

```python
from src.config_loader import load_themes


def test_load_themes_includes_cn_only_count(tmp_path):
    themes = load_themes('config/themes.yml')
    cn_only = [t for t in themes if t.primary_us is None]
    assert len(cn_only) >= 7, f"expected >=7 cn_only themes, got {len(cn_only)}"
    expected_ids = {
        'cn_liquor', 'cn_consumer_staples', 'cn_medical_devices',
        'cn_home_appliances', 'cn_real_estate', 'cn_media', 'cn_dividend',
    }
    actual = {t.id for t in cn_only}
    assert expected_ids.issubset(actual), f"missing: {expected_ids - actual}"


def test_load_themes_cn_only_have_primary_cn():
    themes = load_themes('config/themes.yml')
    for t in themes:
        if t.primary_us is None:
            assert t.primary_cn is not None, f"{t.id} missing primary_cn"
            assert any(cn.code == t.primary_cn for cn in t.cn_etfs), \
                f"{t.id}: primary_cn {t.primary_cn} not in cn_etfs"
```

- [ ] **Step 3.2: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_config_loader.py::test_load_themes_includes_cn_only_count -v 2>&1 | tail -10
```

Expected: FAIL with `expected >=7 cn_only themes, got 0`。

- [ ] **Step 3.3: 实施前实时核对 ETF**

执行一次性脚本核对 ETF 代码/名称/规模（避免代码失效）：

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras python -c "
from src.providers.akshare_em_provider import AkshareEmProvider
p = AkshareEmProvider(throttle_delay=0.5)
codes = ['512690', '159928', '159883', '159996', '512200', '159805', '510880']
for c in codes:
    try:
        df = p.fetch_ohlc(c, lookback_days=5)
        last = df.iloc[-1] if not df.empty else None
        print(f'{c}: OK price={last.close if last is not None else \"-\"}')
    except Exception as e:
        print(f'{c}: FAIL {e}')
" 2>&1 | tail -20
```

Expected: 7 个 code 全部 `OK`。任何一个失败需找替代 ETF 并回到设计评审更新 spec 第 4.1 节，不要硬塞失效代码。

- [ ] **Step 3.4: 追加 7 个主题到 themes.yml**

编辑 `config/themes.yml`，在文件末尾追加（确保与既有主题缩进一致，YAML 顶层是 `themes:` 数组）：

```yaml
  - id: cn_liquor
    name: 白酒
    tags: [白酒, 主要消费]
    primary_cn: '512690'
    cn_etfs:
      - { code: '512690', name: '酒ETF', tracking: '中证酒', match_type: exact }

  - id: cn_consumer_staples
    name: 主要消费
    tags: [消费, 食品饮料]
    primary_cn: '159928'
    cn_etfs:
      - { code: '159928', name: '消费ETF', tracking: '中证主要消费', match_type: exact }

  - id: cn_medical_devices
    name: 医疗器械
    tags: [医疗器械, 医药]
    primary_cn: '159883'
    cn_etfs:
      - { code: '159883', name: '医疗器械ETF', tracking: '中证全指医疗器械', match_type: exact }

  - id: cn_home_appliances
    name: 家电
    tags: [家电, 可选消费]
    primary_cn: '159996'
    cn_etfs:
      - { code: '159996', name: '家电ETF', tracking: '中证全指家电', match_type: exact }

  - id: cn_real_estate
    name: 房地产
    tags: [地产]
    primary_cn: '512200'
    cn_etfs:
      - { code: '512200', name: '地产ETF', tracking: '中证800地产', match_type: exact }

  - id: cn_media
    name: 传媒
    tags: [传媒, 游戏, TMT]
    primary_cn: '159805'
    cn_etfs:
      - { code: '159805', name: '传媒ETF', tracking: '中证传媒', match_type: exact }

  - id: cn_dividend
    name: 红利
    tags: [红利, 高股息]
    primary_cn: '510880'
    cn_etfs:
      - { code: '510880', name: '红利ETF', tracking: '上证红利', match_type: exact }
```

Step 3.3 中若任何 ETF 名称/tracking 与上面常量不符，按实际值调整。

- [ ] **Step 3.5: 运行测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_config_loader.py -v 2>&1 | tail -10
```

Expected: 全部 PASS。

- [ ] **Step 3.6: 等待用户授权后 commit**

```bash
git add config/themes.yml backend/tests/test_config_loader.py
git commit -m "feat(config): add 7 cn-only sector themes (liquor/consumer/medical/etc.)"
```

---

## Task 4: Pipeline 双 strength 计算

**Files:**
- Modify: `backend/src/pipeline.py:73-87`（_collect_us_ohlc）、`:130-136`（_theme_returns）、`:200-235`（strength 计算块）、`:295-340`（输出组装）
- Test: `backend/tests/test_pipeline_compute_outputs.py`

- [ ] **Step 4.1: 写失败测试**

在 `backend/tests/test_pipeline_compute_outputs.py` 追加（如已 import 复用即可）：

```python
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from src.config_loader import load_algo_config
from src.models import ThemeConfig, CnEtfConfig
from src.pipeline import compute_outputs, PipelineMode

BJT = timezone(timedelta(hours=8))


def _fake_ohlc(n=200, base=100.0, drift=0.001):
    rng = np.random.default_rng(42)
    closes = base * np.cumprod(1 + rng.normal(drift, 0.01, n))
    dates = pd.date_range('2025-01-01', periods=n, freq='B')
    return pd.DataFrame({'open': closes, 'high': closes, 'low': closes,
                         'close': closes, 'volume': 1.0, 'amount': 1e8},
                        index=dates)


def test_compute_outputs_cn_only_theme_no_us_strength():
    """纯 A 股主题：us_strength 应为 None，cn_strength 非空，strength == cn_strength。"""
    themes = [
        ThemeConfig(id='mapped', name='M', us_etfs=['SOXX'], primary_us='SOXX',
                    tags=[], cn_etfs=[CnEtfConfig(code='000001', name='X', tracking='T', match_type='exact')]),
        ThemeConfig(id='cn_x', name='X', primary_cn='000002', tags=[],
                    cn_etfs=[CnEtfConfig(code='000002', name='Y', tracking='T2', match_type='exact')]),
    ]
    us_ohlc = {'SOXX': _fake_ohlc(base=100)}
    cn_ohlc = {'000001': _fake_ohlc(base=10), '000002': _fake_ohlc(base=20)}
    algo = load_algo_config('config/algo.yml')
    asof = datetime(2025, 6, 19, 16, 0, tzinfo=BJT)

    themes_json, etfs_json, signals_json, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof, PipelineMode.ARCHIVE,
    )

    by_id = {t['id']: t for t in themes_json['themes']}
    mapped = by_id['mapped']
    cn_only = by_id['cn_x']

    assert mapped['us_strength'] is not None
    assert mapped['cn_strength'] is not None

    assert cn_only['us_strength'] is None
    assert cn_only['cn_strength'] is not None
    assert cn_only['strength'] == cn_only['cn_strength']


def test_compute_outputs_schema_version_bumped():
    themes = [ThemeConfig(id='m', name='M', us_etfs=['SOXX'], primary_us='SOXX',
                          tags=[], cn_etfs=[CnEtfConfig(code='000001', name='X', tracking='T', match_type='exact')])]
    us_ohlc = {'SOXX': _fake_ohlc()}
    cn_ohlc = {'000001': _fake_ohlc()}
    algo = load_algo_config('config/algo.yml')
    asof = datetime(2025, 6, 19, 16, 0, tzinfo=BJT)
    themes_json, _, _, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, [], [], algo, asof, PipelineMode.ARCHIVE,
    )
    assert themes_json['schema_version'] == '1.1'
    assert meta_json['theme_kinds'] == {'mapped': 1, 'cn_only': 0}
```

- [ ] **Step 4.2: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_pipeline_compute_outputs.py::test_compute_outputs_cn_only_theme_no_us_strength tests/test_pipeline_compute_outputs.py::test_compute_outputs_schema_version_bumped -v 2>&1 | tail -25
```

Expected: FAIL，缺 `us_strength`/`cn_strength` 字段或 schema 还是 1.0。

- [ ] **Step 4.3: 修改 _collect_us_ohlc 容错空 us**

编辑 `backend/src/pipeline.py:78-80`，将：

```python
    for t in themes:
        symbols.update(t.us_etfs)
```

替换为：

```python
    for t in themes:
        if t.us_etfs:
            symbols.update(t.us_etfs)
```

- [ ] **Step 4.4: 修改 _theme_returns 容错**

编辑 `backend/src/pipeline.py:132-136`：

```python
def _theme_returns(t: ThemeConfig, us_ohlc: dict[str, pd.DataFrame]) -> Returns:
    if not t.primary_us:
        return Returns()
    df = us_ohlc.get(t.primary_us)
    if df is None or df.empty:
        return Returns()
    return compute_returns(df)
```

- [ ] **Step 4.5: 修改主题 strength 计算块，跳过 cn_only**

编辑 `backend/src/pipeline.py:206-216`（"4) 主题强度"块），替换为：

```python
    # 4) 主题强度（US 池：仅含 mapped 主题）
    k = algo.strength.k_sigmoid
    days = algo.strength.days_in_dim
    cw = algo.strength.composite_weights
    theme_strengths: dict[str, Strength] = {}
    for t in themes:
        if not t.primary_us:
            continue  # 纯 A 股主题不参与 US 池
        r = theme_returns[t.id]
        s = _strength_for_pool(dim_aggregate_return(r, 'short'),
                               theme_dim_rets['short'], k, days['short'])
        m = _strength_for_pool(dim_aggregate_return(r, 'mid'),
                               theme_dim_rets['mid'], k, days['mid'])
        long_s = _strength_for_pool(dim_aggregate_return(r, 'long'),
                                    theme_dim_rets['long'], k, days['long'])
        c = composite_strength(s, m, long_s, cw['short'], cw['mid'], cw['long'])
        theme_strengths[t.id] = Strength(short=s, mid=m, long=long_s, composite=c)
```

并把上方 `theme_dim_rets`（约 `:185` 附近，搜 `theme_dim_rets: dict`）的构造也改为仅含 mapped 主题（保险起见即使现在已经因为 `theme_returns` 空返回而过滤，也显式跳过）：

定位：`theme_dim_rets: dict[DimName, list[float]] = {...}` 这一段，将参与构造的主题循环加 `if not t.primary_us: continue`。完整片段：

```python
    theme_dim_rets: dict[DimName, list[float]] = {
        dim: [
            r for r in (
                dim_aggregate_return(theme_returns[t.id], dim)
                for t in themes if t.primary_us
            ) if r is not None
        ]
        for dim in DIMS
    }
```

(若现有代码结构与上稍异，按"循环 themes 时加 if t.primary_us 过滤"原则微调，保持等价语义。)

- [ ] **Step 4.6: 新增 CN 主题池 strength 计算**

在 `backend/src/pipeline.py` 现有"5) A 股 ETF 强度"块之后（约 `:229` 之后），插入：

```python
    # 5b) CN 主题池强度（全主题双算）
    cn_theme_returns: dict[str, Returns] = {}
    cn_theme_primary: dict[str, str] = {}
    for t in themes:
        code = t.primary_cn or (t.cn_etfs[0].code if t.cn_etfs else None)
        if code is None:
            continue
        cn_theme_primary[t.id] = code
        cn_theme_returns[t.id] = cn_returns.get(code, Returns())

    cn_theme_dim_rets: dict[DimName, list[float]] = {
        dim: [
            r for r in (dim_aggregate_return(cn_theme_returns[tid], dim)
                        for tid in cn_theme_returns)
            if r is not None
        ]
        for dim in DIMS
    }

    cn_theme_strengths: dict[str, Strength] = {}
    for tid, r in cn_theme_returns.items():
        s = _strength_for_pool(dim_aggregate_return(r, 'short'),
                               cn_theme_dim_rets['short'], k, days['short'])
        m = _strength_for_pool(dim_aggregate_return(r, 'mid'),
                               cn_theme_dim_rets['mid'], k, days['mid'])
        long_s = _strength_for_pool(dim_aggregate_return(r, 'long'),
                                    cn_theme_dim_rets['long'], k, days['long'])
        c = composite_strength(s, m, long_s, cw['short'], cw['mid'], cw['long'])
        cn_theme_strengths[tid] = Strength(short=s, mid=m, long=long_s, composite=c)
```

- [ ] **Step 4.7: 修改排名 / Top 计算容纳纯 A 股**

`backend/src/pipeline.py:232-234` 当前是：

```python
    sorted_ids = sorted(theme_strengths.keys(),
                        key=lambda i: theme_strengths[i].composite, reverse=True)
```

替换为（按"主显示 strength = us or cn"统一排名）：

```python
    display_strengths: dict[str, Strength] = {
        t.id: (theme_strengths.get(t.id) or cn_theme_strengths.get(t.id))
        for t in themes
        if theme_strengths.get(t.id) or cn_theme_strengths.get(t.id)
    }
    sorted_ids = sorted(display_strengths.keys(),
                        key=lambda i: display_strengths[i].composite, reverse=True)
```

并在下方 `top_theme = TopTheme(...)` 处（`:303-305`）将：

```python
            id=top_id, name=top_t.name, primary_us=top_t.primary_us,
            composite_strength=theme_strengths[top_id].composite,
```

改为：

```python
            id=top_id, name=top_t.name, primary_us=top_t.primary_us,
            composite_strength=display_strengths[top_id].composite,
```

- [ ] **Step 4.8: 修改 themes.json 输出（schema 1.1 + us/cn strength）**

`backend/src/pipeline.py:322-338` 当前的 themes_json 构造替换为：

```python
    def _strength_dump(s: Strength | None) -> dict[str, Any] | None:
        return s.model_dump() if s else None

    themes_json: dict[str, Any] = {
        'schema_version': '1.1',
        'generated_at': asof_bjt.isoformat(),
        'themes': [
            {
                'id': t.id, 'name': t.name,
                'us_etfs': t.us_etfs,
                'primary_us': t.primary_us,
                'primary_cn': t.primary_cn or cn_theme_primary.get(t.id),
                'tags': t.tags, 'note': t.note,
                'returns': theme_returns[t.id].model_dump() if t.primary_us
                           else cn_theme_returns.get(t.id, Returns()).model_dump(),
                'strength': display_strengths[t.id].model_dump(),
                'us_strength': _strength_dump(theme_strengths.get(t.id)),
                'cn_strength': _strength_dump(cn_theme_strengths.get(t.id)),
                'rank': Rank(
                    short=theme_ranks[t.id], mid=theme_ranks[t.id],
                    long=theme_ranks[t.id], composite=theme_ranks[t.id],
                ).model_dump(),
            } for t in themes if t.id in display_strengths
        ],
    }
```

- [ ] **Step 4.9: 修改 meta.json 输出加 theme_kinds**

先定位 meta_json 构造位置（确认是 dict 直构还是 MetaInfo.model_dump）：

```bash
cd /Users/dreambt/sources/etf-radar/backend && grep -n "meta_json" src/pipeline.py | head -20
```

不论原构造形态如何，在 `compute_outputs` 返回前、最后一次 `meta_json` 赋值之后插入：

```python
    # theme_kinds 是 schema 1.1 新增字段，统计每类主题数量
    if not isinstance(meta_json, dict):
        meta_json = meta_json.model_dump()  # 兜底：若上游返回 MetaInfo 实例
    meta_json['theme_kinds'] = {
        'mapped': sum(1 for t in themes if t.primary_us),
        'cn_only': sum(1 for t in themes if not t.primary_us),
    }
```

确认 `compute_outputs` 返回的 4 元组中 `meta_json` 位置确实是 dict（pipeline.py 现有代码已是 dict）。如不是，按上面 isinstance 兜底转换。

- [ ] **Step 4.10: 运行新测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_pipeline_compute_outputs.py -v 2>&1 | tail -20
```

Expected: 全部 PASS（包括之前可能受影响的既有用例）。

- [ ] **Step 4.11: 跑全 backend 回归**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -10
```

Expected: 全部 PASS。如有 test_signals.py 失败留到 Task 6 处理（应是 ThemeSignal 对纯 A 股的处理）。

- [ ] **Step 4.12: 等待用户授权后 commit**

```bash
git add backend/src/pipeline.py backend/tests/test_pipeline_compute_outputs.py
git commit -m "feat(pipeline): dual strength (us/cn pool) + schema 1.1 + theme_kinds"
```

---

## Task 5: Signal 模块跳过纯 A 股主题

**Files:**
- Modify: `backend/src/scoring/signals.py`、`backend/src/pipeline.py`（theme_signals 循环）
- Test: `backend/tests/test_signals.py`

- [ ] **Step 5.1: 写失败测试**

追加到 `backend/tests/test_signals.py`：

```python
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from src.models import ThemeConfig, CnEtfConfig
from src.pipeline import compute_outputs, PipelineMode
from src.config_loader import load_algo_config

BJT = timezone(timedelta(hours=8))


def _fake_ohlc(n=200, base=100.0):
    rng = np.random.default_rng(7)
    closes = base * np.cumprod(1 + rng.normal(0.001, 0.01, n))
    return pd.DataFrame(
        {'open': closes, 'high': closes, 'low': closes, 'close': closes,
         'volume': 1.0, 'amount': 1e8},
        index=pd.date_range('2025-01-01', periods=n, freq='B'),
    )


def test_cn_only_theme_has_null_signal():
    themes = [
        ThemeConfig(id='cn_x', name='X', primary_cn='000001', tags=[],
                    cn_etfs=[CnEtfConfig(code='000001', name='Y', tracking='T', match_type='exact')]),
    ]
    cn_ohlc = {'000001': _fake_ohlc(base=10)}
    algo = load_algo_config('config/algo.yml')
    asof = datetime(2025, 6, 19, 16, 0, tzinfo=BJT)
    _, _, signals_json, _ = compute_outputs(
        themes, {}, cn_ohlc, [], [], algo, asof, PipelineMode.ARCHIVE,
    )

    ts = [s for s in signals_json['theme_signals'] if s['theme_id'] == 'cn_x'][0]
    assert ts['signal'] is None
    assert ts['trigger_cn_etf'] is None or ts['trigger_cn_etf'] == '000001'
    # SignalsSummary 不应把 None 算入任一类
    summary = signals_json['summary']
    assert summary['resonance_count'] == 0
    assert summary['transmission_count'] == 0
    assert summary['divergence_count'] == 0
```

- [ ] **Step 5.2: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_signals.py::test_cn_only_theme_has_null_signal -v 2>&1 | tail -15
```

Expected: FAIL，可能因为 pipeline 中 `us_str_obj = theme_strengths[t.id]` 对纯 A 股主题 KeyError，或 signal 计算未 None。

- [ ] **Step 5.3: 修改 pipeline theme_signals 循环跳过纯 A 股**

定位 `backend/src/pipeline.py:239-279`（`# 7) 映射分 + 信号` 块的 theme 信号部分），在循环开头加：

```python
    for t in themes:
        if not t.primary_us:
            theme_signals.append(ThemeSignal(
                theme_id=t.id, signal=None, trigger_cn_etf=None,
                votes={'short': None, 'mid': None, 'long': None},
                description=f"{t.name}（A 股本土赛道）",
            ))
            continue
        us_df = us_ohlc.get(t.primary_us)
        # ...（既有逻辑保持不变）
```

并在原 `us_str_obj = theme_strengths[t.id]` 不变（因前面 if 已跳过），其下 PairSignal 循环亦只针对 mapped 主题执行（已经在该 for 内）。

- [ ] **Step 5.4: 运行测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_signals.py -v 2>&1 | tail -15
```

Expected: 全部 PASS。

- [ ] **Step 5.5: 全 backend 回归**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -10
```

Expected: 全部 PASS。

- [ ] **Step 5.6: 等待用户授权后 commit**

```bash
git add backend/src/pipeline.py backend/tests/test_signals.py
git commit -m "feat(signals): skip cn-only themes in resonance/transmission/divergence"
```

---

## Task 6: 升级 JSON Schema 与 fixture

**Files:**
- Modify: `backend/tests/schemas/themes.schema.json`
- Modify: `backend/tests/fixtures/themes_minimal.yml`
- Test: `backend/tests/test_output_schemas.py`

- [ ] **Step 6.1: 写失败测试**

在 `backend/tests/test_output_schemas.py` 追加：

```python
import json
from pathlib import Path
from jsonschema import validate, Draft7Validator


def _schema():
    return json.loads(Path('tests/schemas/themes.schema.json').read_text(encoding='utf-8'))


def test_themes_schema_version_is_1_1():
    s = _schema()
    # schema 自身也声明 1.1，避免被前端误读
    assert s['properties']['schema_version']['const'] == '1.1'


def test_themes_schema_validates_cn_only_entry():
    doc = {
        'schema_version': '1.1',
        'generated_at': '2025-06-19T16:00:00+08:00',
        'themes': [{
            'id': 'cn_x', 'name': 'X',
            'us_etfs': [], 'primary_us': None, 'primary_cn': '000001',
            'tags': [], 'note': '',
            'returns': {'r_1d': None, 'r_5d': None, 'r_20d': None,
                        'r_60d': None, 'r_120d': None, 'r_ytd': None},
            'strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'us_strength': None,
            'cn_strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'rank': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
        }],
    }
    validate(instance=doc, schema=_schema())


def test_themes_schema_validates_mapped_entry():
    doc = {
        'schema_version': '1.1',
        'generated_at': '2025-06-19T16:00:00+08:00',
        'themes': [{
            'id': 'm', 'name': 'M',
            'us_etfs': ['SOXX'], 'primary_us': 'SOXX', 'primary_cn': None,
            'tags': [], 'note': '',
            'returns': {'r_1d': None, 'r_5d': None, 'r_20d': None,
                        'r_60d': None, 'r_120d': None, 'r_ytd': None},
            'strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'us_strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'cn_strength': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
            'rank': {'short': 1, 'mid': 1, 'long': 1, 'composite': 1},
        }],
    }
    validate(instance=doc, schema=_schema())
```

- [ ] **Step 6.2: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_output_schemas.py -v 2>&1 | tail -20
```

Expected: FAIL，因 schema 还是 1.0，缺 `primary_cn`/`us_strength`/`cn_strength`。

- [ ] **Step 6.3: 升级 themes.schema.json 到 1.1**

读取现 schema 后，修改 `backend/tests/schemas/themes.schema.json`：

- `properties.schema_version` 改为 `{"const": "1.1"}`
- `themes.items.properties` 中：
  - `us_etfs`: `{"type": "array", "items": {"type": "string"}}`（保持但移出 required）
  - `primary_us`: `{"type": ["string", "null"]}`
  - 新增 `primary_cn`: `{"type": ["string", "null"]}`
  - 新增 `us_strength`: `{"oneOf": [{"$ref": "#/$defs/strength"}, {"type": "null"}]}`
  - 新增 `cn_strength`: `{"oneOf": [{"$ref": "#/$defs/strength"}, {"type": "null"}]}`
- `themes.items.required` 中移除 `primary_us`（若有）；保留 `id, name, returns, strength, rank, us_etfs`；新增 `primary_cn, us_strength, cn_strength`
- 顶层加 `"$defs": {"strength": {"type": "object", "properties": {"short":{"type":"integer"}, "mid":{"type":"integer"}, "long":{"type":"integer"}, "composite":{"type":"integer"}}, "required": ["short","mid","long","composite"]}}`（若已有则复用）

实施技巧：先 `Read` 现 schema 文件全文，然后用 `Edit` 精准替换字段块，避免全文重写。

- [ ] **Step 6.4: 更新 fixture 补 cn_only 条目**

读 `backend/tests/fixtures/themes_minimal.yml`，在 themes 数组末尾追加：

```yaml
  - id: cn_test_sector
    name: 测试本土赛道
    tags: [测试]
    primary_cn: '999999'
    cn_etfs:
      - { code: '999999', name: '测试ETF', tracking: '测试指数', match_type: exact }
```

- [ ] **Step 6.5: 运行测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest tests/test_output_schemas.py -v 2>&1 | tail -15
```

Expected: 全部 PASS。

- [ ] **Step 6.6: 全 backend 回归**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -10
```

Expected: 全部 PASS。

- [ ] **Step 6.7: 等待用户授权后 commit**

```bash
git add backend/tests/schemas/themes.schema.json backend/tests/fixtures/themes_minimal.yml backend/tests/test_output_schemas.py
git commit -m "feat(schema): bump themes.json schema to 1.1 (us_strength/cn_strength/primary_cn)"
```

---

## Task 7: 前端 Theme zod schema 扩展

**Files:**
- Modify: `frontend/src/types/themes.ts`
- Test: 现有 zod 类型本身无 vitest，靠 TypeScript 编译验证；通过下面 rotation/ThemeRow 测试间接覆盖

- [ ] **Step 7.1: 修改 ThemeSchema**

读 `frontend/src/types/themes.ts`，将 `ThemeSchema` 替换为：

```ts
const ThemeSchema = z.object({
  id: z.string(),
  name: z.string(),
  us_etfs: z.array(z.string()),
  primary_us: z.string().nullable(),
  primary_cn: z.string().nullable(),
  tags: z.array(z.string()),
  note: z.string(),
  returns: ReturnsSchema,
  strength: StrengthSchema,
  us_strength: StrengthSchema.nullable(),
  cn_strength: StrengthSchema.nullable(),
  rank: RankSchema,
});
```

确认 `ThemesFileSchema` 中 `schema_version` 若已是 `z.string()` 即兼容；若是 const，改为 `z.enum(['1.0', '1.1'])`。

- [ ] **Step 7.2: 编译检查**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -20
```

Expected: 0 错误。如有 `Theme.primary_us` 在某处被假定非 null 报错，记录路径，留到 Task 10/11/12 中按需处理（先 `as string` 暂存或先用 `!`，在对应 task 中正式修复）。

- [ ] **Step 7.3: 运行 vitest 验证 mocks/fixtures 未坏**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm test -- --run 2>&1 | tail -15
```

Expected: 全部 PASS（fixtures 在 Task 13 会扩充，本步骤只验证 schema 变更未引起既有 fixtures 解析失败）。

- [ ] **Step 7.4: 等待用户授权后 commit**

```bash
git add frontend/src/types/themes.ts
git commit -m "feat(types): extend Theme schema with primary_cn/us_strength/cn_strength"
```

---

## Task 8: rotation.ts 加 mode 参数

**Files:**
- Modify: `frontend/src/lib/rotation.ts:34-44`
- Test: `frontend/src/lib/__tests__/rotation.test.ts`

- [ ] **Step 8.1: 写失败测试**

在 `frontend/src/lib/__tests__/rotation.test.ts` 追加：

```ts
import { describe, it, expect } from 'vitest';
import { themesToRotationPoints } from '@/lib/rotation';
import type { Theme } from '@/types/themes';

const baseTheme: Theme = {
  id: 'm', name: 'M',
  us_etfs: ['SOXX'], primary_us: 'SOXX', primary_cn: null,
  tags: [], note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short: 50, mid: 50, long: 50, composite: 50 },
  us_strength: { short: 70, mid: 70, long: 70, composite: 70 },
  cn_strength: { short: 30, mid: 30, long: 30, composite: 30 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
};

const cnOnly: Theme = {
  ...baseTheme, id: 'cn_x', name: 'X',
  us_etfs: [], primary_us: null, primary_cn: '000001',
  us_strength: null,
  cn_strength: { short: 80, mid: 80, long: 80, composite: 80 },
};

describe('themesToRotationPoints with mode', () => {
  it('default us mode filters out cn-only themes', () => {
    const pts = themesToRotationPoints([baseTheme, cnOnly], 'us');
    expect(pts).toHaveLength(1);
    expect(pts[0].themeId).toBe('m');
    expect(pts[0].x).toBe(70); // us_strength.long
  });

  it('cn mode includes all themes with cn_strength', () => {
    const pts = themesToRotationPoints([baseTheme, cnOnly], 'cn');
    expect(pts).toHaveLength(2);
    const x = pts.find(p => p.themeId === 'cn_x');
    expect(x?.x).toBe(80);
  });

  it('default param is us (backward compat)', () => {
    const pts = themesToRotationPoints([baseTheme, cnOnly]);
    expect(pts).toHaveLength(1);
  });
});
```

- [ ] **Step 8.2: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotation.test.ts 2>&1 | tail -20
```

Expected: FAIL（缺第二参数支持，或两次调用返回相同）。

- [ ] **Step 8.3: 修改 rotation.ts**

替换 `frontend/src/lib/rotation.ts` 中 `themesToRotationPoints` 函数：

```ts
export type RotationMode = 'us' | 'cn';

export function themesToRotationPoints(
  themes: Theme[],
  mode: RotationMode = 'us',
): RotationPoint[] {
  const pickField = mode === 'us' ? 'us_strength' : 'cn_strength';
  return themes
    .map(t => {
      const s = t[pickField];
      if (!s) return null;
      return {
        themeId: t.id,
        themeName: t.name,
        x: s.long,
        y: s.short,
        size: s.composite,
        quadrant: classifyQuadrant(s.long, s.short),
        tags: t.tags,
      };
    })
    .filter((p): p is RotationPoint => p !== null);
}
```

- [ ] **Step 8.4: 运行测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotation.test.ts 2>&1 | tail -15
```

Expected: PASS。

- [ ] **Step 8.5: 等待用户授权后 commit**

```bash
git add frontend/src/lib/rotation.ts frontend/src/lib/__tests__/rotation.test.ts
git commit -m "feat(rotation): support us/cn mode parameter in themesToRotationPoints"
```

---

## Task 9: ModeToggle 组件

**Files:**
- Create: `frontend/src/components/rotation/ModeToggle.tsx`
- Test: `frontend/src/components/rotation/__tests__/ModeToggle.test.tsx`

- [ ] **Step 9.1: 写失败测试（先建测试文件）**

`frontend/src/components/rotation/__tests__/ModeToggle.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ModeToggle } from '../ModeToggle';

describe('ModeToggle', () => {
  it('renders both modes with counts', () => {
    render(<ModeToggle mode="us" onChange={() => {}} usCount={14} cnCount={21} />);
    expect(screen.getByText(/美股/)).toBeInTheDocument();
    expect(screen.getByText(/A股/)).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(screen.getByText('21')).toBeInTheDocument();
  });

  it('highlights active mode', () => {
    const { rerender } = render(
      <ModeToggle mode="us" onChange={() => {}} usCount={14} cnCount={21} />
    );
    expect(screen.getByRole('button', { name: /美股/ })).toHaveAttribute('aria-pressed', 'true');
    rerender(<ModeToggle mode="cn" onChange={() => {}} usCount={14} cnCount={21} />);
    expect(screen.getByRole('button', { name: /A股/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('calls onChange when switched', () => {
    const fn = vi.fn();
    render(<ModeToggle mode="us" onChange={fn} usCount={14} cnCount={21} />);
    fireEvent.click(screen.getByRole('button', { name: /A股/ }));
    expect(fn).toHaveBeenCalledWith('cn');
  });
});
```

- [ ] **Step 9.2: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/ModeToggle.test.tsx 2>&1 | tail -10
```

Expected: FAIL（module not found）。

- [ ] **Step 9.3: 实现 ModeToggle**

`frontend/src/components/rotation/ModeToggle.tsx`：

```tsx
import type { RotationMode } from '@/lib/rotation';
import { cn } from '@/lib/utils';

interface Props {
  mode: RotationMode;
  onChange: (m: RotationMode) => void;
  usCount: number;
  cnCount: number;
}

export function ModeToggle({ mode, onChange, usCount, cnCount }: Props) {
  const btn = (m: RotationMode, label: string, count: number) => (
    <button
      type="button"
      aria-pressed={mode === m}
      onClick={() => onChange(m)}
      className={cn(
        'px-3 py-1 text-sm border rounded transition',
        mode === m
          ? 'bg-slate-800 text-white border-slate-800'
          : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50',
      )}
    >
      {label} <span className="ml-1 opacity-70">{count}</span>
    </button>
  );

  return (
    <div className="inline-flex gap-1" role="group" aria-label="散点图强度模式">
      {btn('us', '美股强度', usCount)}
      {btn('cn', 'A股强度', cnCount)}
    </div>
  );
}
```

- [ ] **Step 9.4: 运行测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/ModeToggle.test.tsx 2>&1 | tail -10
```

Expected: 3 用例 PASS。

- [ ] **Step 9.5: 等待用户授权后 commit**

```bash
git add frontend/src/components/rotation/ModeToggle.tsx frontend/src/components/rotation/__tests__/ModeToggle.test.tsx
git commit -m "feat(rotation): add ModeToggle component (us/cn strength)"
```

---

## Task 10: RotationPage / RotationScatterWithTrails 集成 mode

**Files:**
- Modify: `frontend/src/pages/RotationPage.tsx`
- Modify: `frontend/src/components/rotation/RotationScatterWithTrails.tsx`

- [ ] **Step 10.1: 准备：定位现有调用点**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && grep -rn "themesToRotationPoints" src/ 2>&1
```

记录所有调用位置，每个都要传 mode。

- [ ] **Step 10.2: RotationPage 加 mode 状态与 ModeToggle**

在 `frontend/src/pages/RotationPage.tsx` 中：

1. import: `import { ModeToggle } from '@/components/rotation/ModeToggle';` `import type { RotationMode } from '@/lib/rotation';`
2. 组件顶部 state：`const [mode, setMode] = useState<RotationMode>('us');`
3. 计算 counts（基于当前 themes 列表）：

```tsx
const usCount = themes.filter(t => t.us_strength !== null).length;
const cnCount = themes.filter(t => t.cn_strength !== null).length;
```

4. 在散点图上方渲染：

```tsx
<div className="flex items-center justify-between mb-3">
  <h2 className="text-base font-semibold">主题轮动</h2>
  <ModeToggle mode={mode} onChange={setMode} usCount={usCount} cnCount={cnCount} />
</div>
```

5. 将 `mode` 透传给 `<RotationScatterWithTrails mode={mode} ... />`

- [ ] **Step 10.3: RotationScatterWithTrails 接受 mode**

在该组件 props 类型加 `mode?: RotationMode`，所有调用 `themesToRotationPoints(themes)` 改为 `themesToRotationPoints(themes, mode ?? 'us')`。trails 历史快照同样按 mode 切换：

```tsx
const trailsPoints = snapshots.map(snap => themesToRotationPoints(snap.themes, mode));
```

历史快照若无 cn_strength（schema 1.0），过滤后该日点缺失自动断点。trails 渲染层对空点应已有兜底（沿用现有 staleness 空心点逻辑），无需新增。

- [ ] **Step 10.4: 编译 & 测试**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -10 && npm test -- --run 2>&1 | tail -15
```

Expected: 0 TS 错误；vitest 全 PASS。如 trails 测试因 snapshots fixture 缺 cn_strength 报错，留到 Task 13 fixture 修复时统一处理。

- [ ] **Step 10.5: 等待用户授权后 commit**

```bash
git add frontend/src/pages/RotationPage.tsx frontend/src/components/rotation/RotationScatterWithTrails.tsx
git commit -m "feat(rotation): wire ModeToggle into RotationPage with us/cn count"
```

---

## Task 11: ThemeRow A 股专属 pill

**Files:**
- Modify: `frontend/src/components/ThemeList/ThemeRow.tsx`
- Test: `frontend/src/components/ThemeList/__tests__/ThemeRow.test.tsx`

- [ ] **Step 11.1: 写失败测试**

`frontend/src/components/ThemeList/__tests__/ThemeRow.test.tsx`：

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeRow } from '../ThemeRow';
import type { Theme } from '@/types/themes';

const mkTheme = (overrides: Partial<Theme> = {}): Theme => ({
  id: 'm', name: '半导体',
  us_etfs: ['SOXX'], primary_us: 'SOXX', primary_cn: null,
  tags: [], note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short: 50, mid: 50, long: 50, composite: 50 },
  us_strength: { short: 50, mid: 50, long: 50, composite: 50 },
  cn_strength: { short: 50, mid: 50, long: 50, composite: 50 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
  ...overrides,
});

describe('ThemeRow A 股专属 pill', () => {
  it('does NOT render pill for mapped theme', () => {
    render(<ThemeRow theme={mkTheme()} />);
    expect(screen.queryByText('A股专属')).toBeNull();
  });

  it('renders pill for cn-only theme', () => {
    render(<ThemeRow theme={mkTheme({
      id: 'cn_x', name: '白酒',
      us_etfs: [], primary_us: null, primary_cn: '512690',
      us_strength: null,
    })} />);
    expect(screen.getByText('A股专属')).toBeInTheDocument();
  });
});
```

如 ThemeRow 当前签名不是 `{ theme }` 单 prop，需要根据现实参数调整 mock 数据（先读源文件）。

- [ ] **Step 11.2: 读 ThemeRow 源码确认 props 签名**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && head -40 src/components/ThemeList/ThemeRow.tsx
```

若 Props 不是 `{ theme: Theme }`，根据实际签名调整 Step 11.1 的测试 mock。

- [ ] **Step 11.2b: 运行测试确认失败**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/ThemeList/__tests__/ThemeRow.test.tsx 2>&1 | tail -15
```

Expected: FAIL（无 'A股专属' 文本）。

- [ ] **Step 11.3: 给 ThemeRow 加 pill**

在 ThemeRow 主题名旁（或最右侧 strength 之前），加：

```tsx
{theme.primary_us === null && (
  <span className="ml-2 inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-slate-100 text-slate-600 border border-slate-200">
    A股专属
  </span>
)}
```

具体插入位置参考现 ThemeRow 中 `theme.name` 渲染处。

- [ ] **Step 11.4: 运行测试确认通过**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/ThemeList/__tests__/ThemeRow.test.tsx 2>&1 | tail -10
```

Expected: 2 用例 PASS。

- [ ] **Step 11.5: 等待用户授权后 commit**

```bash
git add frontend/src/components/ThemeList/ThemeRow.tsx frontend/src/components/ThemeList/__tests__/ThemeRow.test.tsx
git commit -m "feat(ui): show 'A股专属' pill on cn-only theme rows"
```

---

## Task 12: MappingPanel 无映射兜底

**Files:**
- Modify: `frontend/src/components/ThemeDetail/MappingPanel.tsx`

- [ ] **Step 12.1: 读源码**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && cat src/components/ThemeDetail/MappingPanel.tsx | head -40
```

- [ ] **Step 12.2: 加入早期兜底分支**

在 MappingPanel 组件 return 前加：

```tsx
if (theme.primary_us === null) {
  return (
    <div className="rounded border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
      本主题为 A 股本土赛道，无对应美股主题，故不展示映射相关字段。
    </div>
  );
}
```

- [ ] **Step 12.3: 验证 TS 编译与既有测试**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -5 && npm test -- --run 2>&1 | tail -10
```

Expected: 0 TS 错误，既有测试不破坏。

- [ ] **Step 12.4: 等待用户授权后 commit**

```bash
git add frontend/src/components/ThemeDetail/MappingPanel.tsx
git commit -m "feat(ui): MappingPanel fallback for cn-only themes"
```

---

## Task 13: FilterBar 仅看 A 股专属 checkbox + fixtures 扩充

**Files:**
- Modify: `frontend/src/components/FilterBar/index.tsx`
- Modify: `frontend/src/__fixtures__/snapshots.ts`
- Modify: 调用 FilterBar 的父组件（一般是 RadarPage）

- [ ] **Step 13.1: fixtures 扩充 cn_only 主题**

在 `frontend/src/__fixtures__/snapshots.ts` 的 themes 数组中新增至少 1 个 cn_only 条目（`primary_us: null, primary_cn: '512690', us_strength: null, cn_strength: {...}`），并把 schema_version 改为 `'1.1'`。

- [ ] **Step 13.2: FilterBar 加 checkbox**

读 `frontend/src/components/FilterBar/index.tsx`，在现有 filter 控件旁加：

```tsx
<label className="inline-flex items-center gap-1 text-sm text-slate-600">
  <input
    type="checkbox"
    checked={onlyCnOnly}
    onChange={e => onOnlyCnOnlyChange(e.target.checked)}
  />
  仅看 A 股专属
</label>
```

并在 props 中加 `onlyCnOnly: boolean; onOnlyCnOnlyChange: (v: boolean) => void;`。

- [ ] **Step 13.3: 父组件接入过滤**

先定位 FilterBar 的调用方（通常是 `frontend/src/pages/RadarPage.tsx`，以 grep 结果为准）：

```bash
cd /Users/dreambt/sources/etf-radar/frontend && grep -rn "<FilterBar" src/ 2>&1
```

在调用 FilterBar 的页面中加：

```tsx
const [onlyCnOnly, setOnlyCnOnly] = useState(false);
const visibleThemes = onlyCnOnly
  ? themes.filter(t => t.primary_us === null)
  : themes;
```

并把 `visibleThemes` 替代原 `themes` 传给 ThemeList。FilterBar JSX 加 `onlyCnOnly={onlyCnOnly} onOnlyCnOnlyChange={setOnlyCnOnly}`。

- [ ] **Step 13.4: 编译 + 测试**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -5 && npm test -- --run 2>&1 | tail -15
```

Expected: 0 TS 错误，所有 vitest PASS。

- [ ] **Step 13.5: 等待用户授权后 commit**

```bash
git add frontend/src/components/FilterBar/index.tsx frontend/src/__fixtures__/snapshots.ts frontend/src/pages/RadarPage.tsx
git commit -m "feat(ui): add '仅看 A 股专属' filter checkbox"
```

---

## Task 14: 端到端冒烟 + 回归

**Files:**
- 无新增，跑现有 backend + frontend + 一次 pipeline backfill

- [ ] **Step 14.1: 跑全后端 + 全前端测试**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -10
cd /Users/dreambt/sources/etf-radar/frontend && npm test -- --run 2>&1 | tail -15
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -5
cd /Users/dreambt/sources/etf-radar/frontend && npm run lint 2>&1 | tail -10
```

Expected: 全 PASS / 0 错误。

- [ ] **Step 14.2: 跑一次今日 backfill 验证真实数据**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras python -m src.pipeline 2>&1 | tail -30
```

或用现有 backfill 脚本写入临时目录（不污染 data/）：

```bash
cd /Users/dreambt/sources/etf-radar/backend && DATA_DIR=/tmp/etf-radar-verify uv run --all-extras python scripts/backfill_snapshots.py --date 2026-06-19 2>&1 | tail -30
```

Expected: pipeline 完成无报错；输出 `data/snapshots/2026-06-19/themes.json`（或 /tmp 路径）。

- [ ] **Step 14.3: 校验输出数量与字段**

```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras python -c "
import json
p = 'data/snapshots/2026-06-19/themes.json'  # 或 /tmp 路径
d = json.load(open(p))
print('schema_version:', d['schema_version'])
print('themes_total:', len(d['themes']))
mapped = [t for t in d['themes'] if t['primary_us']]
cn_only = [t for t in d['themes'] if not t['primary_us']]
print('mapped:', len(mapped), 'cn_only:', len(cn_only))
assert d['schema_version'] == '1.1'
assert len(cn_only) == 7
assert all(t['cn_strength'] is not None for t in d['themes'])
print('OK')
"
```

Expected: `schema_version: 1.1` / `themes_total: 21` / `mapped: 14` / `cn_only: 7` / `OK`。

- [ ] **Step 14.4: 启动 dev server 人工冒烟**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm run dev
```

人工或用 playwright 验证：
1. RotationPage 默认显示 14 个散点
2. 切到 A 股强度 → 显示 21 个散点
3. ThemeList 出现 7 个新主题，名旁有 A 股专属 pill
4. 点开任一新主题 → MappingPanel 显示"A 股本土赛道"提示
5. 勾选"仅看 A 股专属" → 列表只剩 7 个

- [ ] **Step 14.5: 等待用户授权后 commit 数据快照（如生成了真实快照）**

```bash
git add data/snapshots/2026-06-19/
git commit -m "data: regenerate snapshot 2026-06-19 with schema 1.1 (14 mapped + 7 cn_only themes)"
```

如步骤 14.2 用了 /tmp 目录则跳过本步。

---

## 验收清单（与 spec 第 9 节对齐）

完成以下全部为 done：

- [ ] `config/themes.yml` 含 21 个主题（14 mapped + 7 cn_only），全部通过 model 校验
- [ ] 最新快照 `themes.json` schema_version=1.1，21 主题全部有 cn_strength，14 主题额外有 us_strength
- [ ] ThemeList 按 strength.composite 融合排序，纯 A 股主题显示 A 股专属 pill
- [ ] 散点图默认美股模式（14 点），切到 A 股模式显示 21 点
- [ ] 所有 backend pytest 通过
- [ ] 所有 frontend vitest 通过 + tsc 无错误 + lint 无错误
- [ ] 历史快照（schema 1.0）能正常加载，A 股模式下显示空心点轨迹（人工验证）
- [ ] ThemeDetail 中纯 A 股主题的 MappingPanel 显示无映射提示
- [ ] FilterBar 的"仅看 A 股专属"过滤生效

---

## 风险提示

1. **Step 3.3 ETF 实时核对失败**：若有 ETF 代码失效，必须更换；不要硬塞代码导致后续 pipeline run 报错。失败时回到设计文档第 4.1 节更新替代项后再继续。
2. **Step 4.7 排名口径**：现 `theme_ranks` 当前实现是单一 composite 排名套到 short/mid/long 四字段。变更后用 `display_strengths` 而非 `theme_strengths`，主题数从 14 → 21，影响所有现有快照页面的 rank 数字。若用户对 rank 数字有强烈视觉依赖，需评估。本计划维持现有 rank 字段语义，仅扩容分母。
3. **Step 5.3 PairSignal 数量**：纯 A 股主题不产生 PairSignal，signals_json 的 pair_signals 数组长度减少。若有下游消费方依赖 pair_signals 总数等于 sum(cn_etfs)，需通知。
4. **历史快照不回填**：schema 1.0 的快照在 A 股模式下点缺失是预期行为，不要尝试给老快照补 cn_strength（数据源不变化，强行算出来误导用户）。
