# CN ETF Provider Chain 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入可扩展的 CN provider chain 机制（EM 主源 → sina 备用源），消除当前 GitHub Actions 中 EM 失败导致的醒目"Provider 降级"警告，meta 显式区分 `ok / fallback / degraded` 三态。

**Architecture:** chain 逻辑放在 pipeline 层（`_collect_cn_ohlc` 接收 `providers: list[EtfDataProvider]`），各 provider 独立可测；单 symbol 内即时切换（首选失败立即试下一个），不再等 60s second-pass；meta 新增 `fallback_symbols: dict[str, str]` 记录哪些 symbol 走了哪个备用源；前端 `StaleBanner` 增加橙色 warning 中间态。

**Tech Stack:** Python 3.11 + pydantic + akshare + pytest（backend）; React 19 + TypeScript + zod + base-ui + vitest（frontend）。

**关联 Spec:** `docs/superpowers/specs/2026-06-19-cn-provider-chain-design.md`

---

## File Structure

**Backend:**

| File | 操作 | 职责 |
|---|---|---|
| `backend/src/providers/akshare_em_provider.py` | 由 `akshare_provider.py` 重命名 | 东方财富 EM 源，类改名 `AkshareEmProvider`，name='akshare-em' |
| `backend/src/providers/akshare_sina_provider.py` | 新建 | 新浪源，class `AkshareSinaProvider`，name='akshare-sina' |
| `backend/src/providers/__init__.py` | 修改 | 导出公开 API |
| `backend/src/etl/standardize.py` | 修改 | source Literal 加 `'akshare-sina'` 分支 |
| `backend/src/models.py` | 修改 | `ProviderStatus` 加 `'fallback'`；`MetaInfo` 加 `fallback_symbols` |
| `backend/src/pipeline.py` | 修改 | `_collect_cn_ohlc` 接收 providers list；`compute_outputs` 接收 `cn_fallback_map`；`run_pipeline` 注入 providers |
| `backend/tests/schemas/meta.schema.json` | 修改 | 状态枚举 + `fallback_symbols` |
| `backend/tests/test_akshare_em_provider.py` | 由 `test_akshare_provider.py` 重命名 | patch 路径与类名同步 |
| `backend/tests/test_akshare_sina_provider.py` | 新建 | sina provider 单元测试 |
| `backend/tests/test_pipeline_provider_chain.py` | 新建 | chain 算法集成测试 |
| `backend/tests/test_pipeline_smoke.py` | 修改 | 适配 `_collect_cn_ohlc` 新签名 |
| `backend/tests/test_pipeline_compute_outputs.py` | 修改 | 适配 `compute_outputs` 新参数 |

**Frontend:**

| File | 操作 | 职责 |
|---|---|---|
| `frontend/src/types/meta.ts` | 修改 | `ProviderStatus` 加 `'fallback'`；`fallback_symbols` |
| `frontend/src/types/__tests__/schemas.test.ts` | 修改 | 测试新 schema 解析 |
| `frontend/src/components/ui/alert.tsx` | 修改 | 加 `warning` variant |
| `frontend/src/components/Header/StaleBanner.tsx` | 修改 | 三态优先级实现 |
| `frontend/src/components/Header/__tests__/StaleBanner.test.tsx` | 新建 | 三态文案 + 优先级测试 |

---

## Task 1: 重命名 AkshareProvider → AkshareEmProvider

**Files:**
- Rename: `backend/src/providers/akshare_provider.py` → `backend/src/providers/akshare_em_provider.py`
- Rename: `backend/tests/test_akshare_provider.py` → `backend/tests/test_akshare_em_provider.py`

- [ ] **Step 1: git mv 文件并改 patch 路径**

```bash
cd /Users/dreambt/sources/etf-radar
git mv backend/src/providers/akshare_provider.py backend/src/providers/akshare_em_provider.py
git mv backend/tests/test_akshare_provider.py backend/tests/test_akshare_em_provider.py
```

- [ ] **Step 2: 修改 `backend/src/providers/akshare_em_provider.py`**

将类名和 `name` 改为：

```python
class AkshareEmProvider(EtfDataProvider):
    """A 股场内 ETF 数据源 (东方财富, 通过 akshare)."""

    name = 'akshare-em'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        # 用 BJT 时区确定 A 股市场的"今天" (避免 UTC 服务器 off-by-one)
        end = datetime.now(tz=BJT).date()
        start = end - timedelta(days=int(lookback_days * 1.6))  # 含周末+节假日缓冲
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                df = ak.fund_etf_hist_em(
                    symbol=symbol,
                    period='daily',
                    start_date=start.strftime('%Y%m%d'),
                    end_date=end.strftime('%Y%m%d'),
                    adjust='qfq',
                )
                if df is None or df.empty:
                    raise EmptyDataError(f'akshare-em empty for {symbol}')
                return standardize_ohlc(df, source='akshare')
            except EmptyDataError:
                raise
            except Exception as e:
                last_exc = e
                log.warning(f'akshare-em attempt {attempt+1} failed for {symbol}: {e}')
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        raise ProviderError(f'akshare-em failed after {self.max_retries} retries: {last_exc}')
```

- [ ] **Step 3: 修改 `backend/tests/test_akshare_em_provider.py`**

全文替换：
- `from src.providers.akshare_provider import AkshareProvider` → `from src.providers.akshare_em_provider import AkshareEmProvider`
- `src.providers.akshare_provider.ak.fund_etf_hist_em` → `src.providers.akshare_em_provider.ak.fund_etf_hist_em`
- `src.providers.akshare_provider.time.sleep` → `src.providers.akshare_em_provider.time.sleep`
- `AkshareProvider(` → `AkshareEmProvider(`

- [ ] **Step 4: 在 `backend/src/pipeline.py` 中更新 import**

```python
# 第 47 行原:
from .providers.akshare_provider import AkshareProvider
# 改为:
from .providers.akshare_em_provider import AkshareEmProvider
```

不修改 `run_pipeline` 中的 `ak_provider = AkshareProvider()` —— 留到 Task 8 一起改。这里暂时把这行改为：

```python
# 第 408 行原:
ak_provider = AkshareProvider()
# 改为:
ak_provider = AkshareEmProvider()
```

- [ ] **Step 5: 全仓库搜索残留引用**

```bash
cd /Users/dreambt/sources/etf-radar
rg -n "AkshareProvider|akshare_provider" --type py
```

期望输出：仅 git 历史记忆相关，无 `.py` 源码引用。

- [ ] **Step 6: 跑测试验证**

```bash
cd backend && uv run --all-extras pytest tests/test_akshare_em_provider.py -v 2>&1 | tail -20
```

期望：所有测试通过。

- [ ] **Step 7: 提交**

```bash
git add backend/src/providers/akshare_em_provider.py \
        backend/tests/test_akshare_em_provider.py \
        backend/src/pipeline.py
git commit -m "refactor(providers): rename AkshareProvider to AkshareEmProvider"
```

---

## Task 2: 实现 AkshareSinaProvider (TDD)

**Files:**
- Create: `backend/tests/test_akshare_sina_provider.py`
- Create: `backend/src/providers/akshare_sina_provider.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_akshare_sina_provider.py`**

```python
"""AkshareSinaProvider 单元测试"""
import pandas as pd  # type: ignore[import-untyped]
import pytest
from unittest.mock import patch, MagicMock
from src.providers.akshare_sina_provider import AkshareSinaProvider
from src.providers.base import EmptyDataError, ProviderError


@pytest.mark.parametrize('em_code, expected_sina', [
    ('159755', 'sz159755'),
    ('162411', 'sz162411'),
    ('512000', 'sh512000'),
    ('588000', 'sh588000'),
    ('600000', 'sh600000'),
])
def test_to_sina_symbol_mapping(em_code: str, expected_sina: str) -> None:
    assert AkshareSinaProvider._to_sina_symbol(em_code) == expected_sina


def test_to_sina_symbol_unknown_prefix_raises() -> None:
    with pytest.raises(ValueError, match='unknown CN ETF symbol prefix'):
        AkshareSinaProvider._to_sina_symbol('999999')


@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_fetch_ohlc_success(mock_hist: MagicMock) -> None:
    fake = pd.DataFrame({
        'date': pd.to_datetime(['2026-06-17', '2026-06-18']),
        'open': [1.0, 1.05], 'high': [1.1, 1.08],
        'low': [0.9, 1.02], 'close': [1.05, 1.06],
        'volume': [10000, 12000], 'amount': [10500.0, 12700.0],
    })
    mock_hist.return_value = fake
    p = AkshareSinaProvider()
    df = p.fetch_ohlc('512000', 5)
    assert not df.empty
    assert df['amount'].iloc[-1] == 12700.0
    # 验证 sina 前缀映射
    mock_hist.assert_called_once_with(symbol='sh512000')


@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_fetch_ohlc_empty_raises(mock_hist: MagicMock) -> None:
    mock_hist.return_value = pd.DataFrame()
    p = AkshareSinaProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('512000', 5)


@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_fetch_ohlc_none_raises(mock_hist: MagicMock) -> None:
    mock_hist.return_value = None
    p = AkshareSinaProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('512000', 5)


@patch('src.providers.akshare_sina_provider.time.sleep')
@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_retries_then_succeeds(mock_hist: MagicMock, mock_sleep: MagicMock) -> None:
    good = pd.DataFrame({
        'date': pd.to_datetime(['2026-06-18']),
        'open': [1.0], 'high': [1.1], 'low': [0.9],
        'close': [1.05], 'volume': [10000], 'amount': [10500.0],
    })
    mock_hist.side_effect = [Exception('timeout'), Exception('timeout'), good]
    p = AkshareSinaProvider(max_retries=3, base_delay=2.0)
    df = p.fetch_ohlc('512000', 5)
    assert not df.empty
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(2.0)
    mock_sleep.assert_any_call(4.0)


@patch('src.providers.akshare_sina_provider.time.sleep')
@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_all_retries_exhausted_raises(
    mock_hist: MagicMock, mock_sleep: MagicMock,
) -> None:
    mock_hist.side_effect = ConnectionError('network fail')
    p = AkshareSinaProvider(max_retries=3, base_delay=0.01)
    with pytest.raises(ProviderError, match='network fail'):
        p.fetch_ohlc('512000', 5)
    assert mock_hist.call_count == 3


@patch('src.providers.akshare_sina_provider.ak.fund_etf_hist_sina')
def test_lookback_days_tail_applied(mock_hist: MagicMock) -> None:
    """sina 返回全历史，应按 lookback_days * 1.6 截尾"""
    n_rows = 1000
    dates = pd.date_range('2020-01-01', periods=n_rows, freq='D')
    fake = pd.DataFrame({
        'date': dates,
        'open': [1.0] * n_rows, 'high': [1.0] * n_rows,
        'low': [1.0] * n_rows, 'close': [1.0] * n_rows,
        'volume': [100] * n_rows, 'amount': [100.0] * n_rows,
    })
    mock_hist.return_value = fake
    p = AkshareSinaProvider()
    df = p.fetch_ohlc('512000', lookback_days=100)
    # tail(int(100 * 1.6)) = tail(160)
    assert len(df) == 160
```

- [ ] **Step 2: 运行测试，验证全部失败**

```bash
cd backend && uv run --all-extras pytest tests/test_akshare_sina_provider.py -v 2>&1 | tail -10
```

期望：FAIL（模块不存在）。

- [ ] **Step 3: 实现 `backend/src/providers/akshare_sina_provider.py`**

```python
"""akshare 新浪财经数据源 — A 股 ETF 备用源 (无前复权)"""
import time
import logging
import pandas as pd  # type: ignore[import-untyped]
import akshare as ak  # type: ignore[import-untyped]
from .base import EtfDataProvider, ProviderError, EmptyDataError
from ..etl.standardize import standardize_ohlc

log = logging.getLogger(__name__)


class AkshareSinaProvider(EtfDataProvider):
    """A 股场内 ETF 数据源 (新浪财经, 通过 akshare).

    注意:
    - sina 接口无 adjust 参数，返回**不复权**数据，与 EM 源前复权数据存在分红日跳跃差异。
    - 仅作为 EM 主源失败时的备用 fallback 使用。
    - sina 接口返回**全历史**数据，按 lookback_days 截尾。
    """

    name = 'akshare-sina'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        sina_symbol = self._to_sina_symbol(symbol)
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                df = ak.fund_etf_hist_sina(symbol=sina_symbol)
                if df is None or df.empty:
                    raise EmptyDataError(f'akshare-sina empty for {symbol}')
                df_recent = df.tail(int(lookback_days * 1.6))
                return standardize_ohlc(df_recent, source='akshare-sina')
            except EmptyDataError:
                raise
            except Exception as e:
                last_exc = e
                log.warning(f'akshare-sina attempt {attempt+1} failed for {symbol}: {e}')
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        raise ProviderError(f'akshare-sina failed after {self.max_retries} retries: {last_exc}')

    @staticmethod
    def _to_sina_symbol(em_symbol: str) -> str:
        """EM symbol → sina symbol prefix.

        深市 ETF: 159xxx, 162xxx → sz{symbol}
        沪市 ETF: 5xxxxx, 6xxxxx → sh{symbol}
        """
        if em_symbol.startswith('1'):
            return f'sz{em_symbol}'
        if em_symbol.startswith(('5', '6')):
            return f'sh{em_symbol}'
        raise ValueError(f'unknown CN ETF symbol prefix: {em_symbol}')
```

注：实现依赖 Task 3 完成的 `standardize_ohlc(source='akshare-sina')` 分支。先实现本 task，Task 3 完成后测试才能全绿。

- [ ] **Step 4: 运行测试验证不依赖 standardize 的部分通过**

```bash
cd backend && uv run --all-extras pytest tests/test_akshare_sina_provider.py::test_to_sina_symbol_mapping tests/test_akshare_sina_provider.py::test_to_sina_symbol_unknown_prefix_raises tests/test_akshare_sina_provider.py::test_fetch_ohlc_empty_raises tests/test_akshare_sina_provider.py::test_fetch_ohlc_none_raises -v 2>&1 | tail -15
```

期望：4 个测试 PASS。

- [ ] **Step 5: 暂不提交**

依赖 standardize 分支，留到 Task 3 完成后一起提交。

---

## Task 3: standardize_ohlc 增加 sina 分支

**Files:**
- Modify: `backend/src/etl/standardize.py`

- [ ] **Step 1: 修改 `backend/src/etl/standardize.py`**

```python
"""把 yfinance / akshare 的 DataFrame 列名/时区/类型统一

调用方约定:
- yfinance: 使用 `auto_adjust=True` 调用 Ticker.history(), 返回的 Close 列已是
  复权后价格, 不会同时包含 'Adj Close' 列。
- akshare (EM): 使用 adjust='qfq' 调用 fund_etf_hist_em(), 返回前复权数据。
- akshare-sina: 调用 fund_etf_hist_sina(), 返回**不复权**数据，列名已为英文。
"""
from typing import Literal
import pandas as pd  # type: ignore[import-untyped]

STANDARD_COLUMNS: list[str] = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']

YFINANCE_MAP: dict[str, str] = {
    'Date': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low',
    'Close': 'close', 'Volume': 'volume',
    # 注: 不映射 'Adj Close' — 假设调用方使用 auto_adjust=True, Close 即复权价
}

AKSHARE_MAP: dict[str, str] = {
    '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low',
    '收盘': 'close', '成交量': 'volume', '成交额': 'amount',
}

# sina 接口已返回英文列名，仅需保留 STANDARD_COLUMNS 子集
AKSHARE_SINA_MAP: dict[str, str] = {
    'date': 'date', 'open': 'open', 'high': 'high', 'low': 'low',
    'close': 'close', 'volume': 'volume', 'amount': 'amount',
}


def standardize_ohlc(
    df: pd.DataFrame,
    source: Literal['yfinance', 'akshare', 'akshare-sina'],
) -> pd.DataFrame:
    if source == 'yfinance':
        mapping = YFINANCE_MAP
    elif source == 'akshare':
        mapping = AKSHARE_MAP
    elif source == 'akshare-sina':
        mapping = AKSHARE_SINA_MAP
    else:
        raise ValueError(f'unknown source: {source}')

    if df.index.name is not None and df.index.name in mapping:
        df = df.reset_index()

    df = df.rename(columns=mapping)
    if 'amount' not in df.columns:
        df['amount'] = pd.NA
    df['date'] = pd.to_datetime(df['date'], utc=True)
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df[STANDARD_COLUMNS].sort_values('date').reset_index(drop=True)
```

- [ ] **Step 2: 跑 Task 2 全部测试，验证 sina 测试通过**

```bash
cd backend && uv run --all-extras pytest tests/test_akshare_sina_provider.py -v 2>&1 | tail -20
```

期望：所有测试通过。

- [ ] **Step 3: 跑 standardize 现有测试，验证未回归**

```bash
cd backend && uv run --all-extras pytest tests/ -k "standardize" -v 2>&1 | tail -10
```

期望：现有 yfinance/akshare 路径未回归。

- [ ] **Step 4: 提交（Task 2 + Task 3 一起）**

```bash
git add backend/src/providers/akshare_sina_provider.py \
        backend/tests/test_akshare_sina_provider.py \
        backend/src/etl/standardize.py
git commit -m "feat(providers): add AkshareSinaProvider as CN data fallback source"
```

---

## Task 4: models.py 扩展 ProviderStatus + MetaInfo.fallback_symbols

**Files:**
- Modify: `backend/src/models.py`

- [ ] **Step 1: 修改 `backend/src/models.py`**

第 7 行原:
```python
ProviderStatus = Literal['ok', 'degraded', 'stale']
```
改为:
```python
ProviderStatus = Literal['ok', 'fallback', 'degraded', 'stale']
```

`MetaInfo` 类（第 153 行附近）：
```python
class MetaInfo(BaseModel):
    schema_version: str = '1.1'
    last_full_refresh: FullRefreshTimes
    last_intraday_refresh: Optional[str] = None
    providers: dict[str, ProviderInfo]
    failed_symbols: list[str] = Field(default_factory=list)
    fallback_symbols: dict[str, str] = Field(default_factory=dict)
    stale_minutes: int = 0
    calendar: CalendarInfo
    backfilled: bool = False
```

变更点：
- `schema_version` 默认值 `'1.0'` → `'1.1'`
- 在 `failed_symbols` 之后新增 `fallback_symbols: dict[str, str] = Field(default_factory=dict)`

- [ ] **Step 2: 运行所有 backend 测试，确认未破坏现有断言**

```bash
cd backend && uv run --all-extras pytest -x 2>&1 | tail -15
```

期望：除 pipeline 测试可能因 fallback_symbols 缺失断言失败外，其他全部 PASS。如有意外失败，记录后继续 Task 5；不要回退。

- [ ] **Step 3: 暂不提交**

等 Task 5 schema 文件一起提交。

---

## Task 5: meta.schema.json 更新

**Files:**
- Modify: `backend/tests/schemas/meta.schema.json`

- [ ] **Step 1: 修改 `backend/tests/schemas/meta.schema.json`**

将两处 `"enum": ["ok", "degraded", "stale"]` 改为：
```json
"enum": ["ok", "fallback", "degraded", "stale"]
```

在 `required` 数组顶部加 `"fallback_symbols"` 不是必需的（向前兼容旧 meta），但在 `properties` 段补充字段定义。在 `failed_symbols` 之后新增：

```json
"fallback_symbols": {
  "type": "object",
  "additionalProperties": { "type": "string" }
}
```

完整 properties 调整后片段示意（保留其他字段不动）：

```json
{
  "properties": {
    ...
    "failed_symbols": { "type": "array", "items": { "type": "string" } },
    "fallback_symbols": {
      "type": "object",
      "additionalProperties": { "type": "string" }
    },
    "stale_minutes": { "type": "integer", "minimum": 0 },
    ...
  }
}
```

- [ ] **Step 2: 提交（Task 4 + Task 5）**

```bash
git add backend/src/models.py backend/tests/schemas/meta.schema.json
git commit -m "feat(models): add fallback ProviderStatus and MetaInfo.fallback_symbols"
```

---

## Task 6: `_collect_cn_ohlc` 改造为 provider chain (TDD)

**Files:**
- Create: `backend/tests/test_pipeline_provider_chain.py`
- Modify: `backend/src/pipeline.py`

- [ ] **Step 1: 写失败测试 `backend/tests/test_pipeline_provider_chain.py`**

```python
"""provider chain 集成测试: _collect_cn_ohlc 的多源 fallback 行为"""
import pandas as pd  # type: ignore[import-untyped]
import pytest
from unittest.mock import MagicMock, patch
from src.models import CnEtfConfig, ThemeConfig
from src.pipeline import _collect_cn_ohlc
from src.providers.base import EmptyDataError, EtfDataProvider, ProviderError


def _make_provider(name: str, success_codes: set[str]) -> EtfDataProvider:
    """Mock provider: 对 success_codes 返回 OHLC，其他 raise ProviderError"""
    mock = MagicMock(spec=EtfDataProvider)
    mock.name = name

    def fetch(symbol: str, lookback_days: int) -> pd.DataFrame:
        if symbol in success_codes:
            return pd.DataFrame({
                'date': pd.to_datetime(['2026-06-18'], utc=True),
                'open': [1.0], 'high': [1.1], 'low': [0.9],
                'close': [1.05], 'volume': [10000], 'amount': [10500.0],
            })
        raise ProviderError(f'mock {name} fail for {symbol}')

    mock.fetch_ohlc.side_effect = fetch
    return mock


def _themes_with(codes: list[str]) -> list[ThemeConfig]:
    return [
        ThemeConfig(
            id='t1', name='T1', us_etfs=['SPY'], primary_us='SPY', tags=[], note='',
            cn_etfs=[CnEtfConfig(code=c, name=c, tracking='', match_type='exact') for c in codes],
        )
    ]


@patch('src.pipeline.time.sleep')
def test_all_primary_success(mock_sleep: MagicMock) -> None:
    """所有 symbol 都在主源拿到 → fallback_map={}, failed=[]"""
    themes = _themes_with(['512000', '159755'])
    primary = _make_provider('akshare-em', {'512000', '159755'})
    secondary = _make_provider('akshare-sina', set())
    ohlc, fallback_map, failed = _collect_cn_ohlc(themes, [primary, secondary])
    assert set(ohlc.keys()) == {'512000', '159755'}
    assert fallback_map == {}
    assert failed == []
    # secondary 完全不被调用
    secondary.fetch_ohlc.assert_not_called()


@patch('src.pipeline.time.sleep')
def test_partial_fallback(mock_sleep: MagicMock) -> None:
    """部分主源失败，备用源接力 → fallback_map 记录正确"""
    themes = _themes_with(['512000', '159755', '588000'])
    primary = _make_provider('akshare-em', {'512000'})          # 主源只能拿到 512000
    secondary = _make_provider('akshare-sina', {'159755', '588000'})  # 备用源接力
    ohlc, fallback_map, failed = _collect_cn_ohlc(themes, [primary, secondary])
    assert set(ohlc.keys()) == {'512000', '159755', '588000'}
    assert fallback_map == {'159755': 'akshare-sina', '588000': 'akshare-sina'}
    assert failed == []


@patch('src.pipeline.time.sleep')
def test_both_sources_fail(mock_sleep: MagicMock) -> None:
    """双源都失败 → failed_symbols 含该 symbol"""
    themes = _themes_with(['512000', '159755'])
    primary = _make_provider('akshare-em', {'512000'})
    secondary = _make_provider('akshare-sina', set())  # 备用源也全失败
    ohlc, fallback_map, failed = _collect_cn_ohlc(themes, [primary, secondary])
    assert set(ohlc.keys()) == {'512000'}
    assert fallback_map == {}
    assert failed == ['159755']


@patch('src.pipeline.time.sleep')
def test_immediate_switch_no_60s_wait(mock_sleep: MagicMock) -> None:
    """验证不再有 60s second-pass: sleep 调用不应出现 60.0 数值"""
    themes = _themes_with(['512000', '159755'])
    primary = _make_provider('akshare-em', {'512000'})
    secondary = _make_provider('akshare-sina', {'159755'})
    _collect_cn_ohlc(themes, [primary, secondary])
    sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
    assert all(v < 5.0 for v in sleep_values), f'unexpected long sleep: {sleep_values}'


@patch('src.pipeline.time.sleep')
def test_secondary_tried_only_when_primary_fails(mock_sleep: MagicMock) -> None:
    """主源成功时，备用源不应被尝试"""
    themes = _themes_with(['512000'])
    primary = _make_provider('akshare-em', {'512000'})
    secondary = MagicMock(spec=EtfDataProvider)
    secondary.name = 'akshare-sina'
    _collect_cn_ohlc(themes, [primary, secondary])
    secondary.fetch_ohlc.assert_not_called()


@patch('src.pipeline.time.sleep')
def test_empty_data_treated_as_failure(mock_sleep: MagicMock) -> None:
    """主源返回 EmptyDataError 时应尝试备用源（不是直接 raise）"""
    themes = _themes_with(['512000'])
    primary = MagicMock(spec=EtfDataProvider)
    primary.name = 'akshare-em'
    primary.fetch_ohlc.side_effect = EmptyDataError('empty')
    secondary = _make_provider('akshare-sina', {'512000'})
    ohlc, fallback_map, failed = _collect_cn_ohlc(themes, [primary, secondary])
    assert '512000' in ohlc
    assert fallback_map == {'512000': 'akshare-sina'}
    assert failed == []
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && uv run --all-extras pytest tests/test_pipeline_provider_chain.py -v 2>&1 | tail -15
```

期望：FAIL（_collect_cn_ohlc 签名不匹配，返回 tuple 长度不对）。

- [ ] **Step 3: 修改 `backend/src/pipeline.py` 的 `_collect_cn_ohlc`**

整体替换第 88-133 行的 `_collect_cn_ohlc` 函数为：

```python
def _collect_cn_ohlc(
    themes: list[ThemeConfig],
    providers: list[EtfDataProvider],
) -> tuple[dict[str, pd.DataFrame], dict[str, str], list[str]]:
    """A 股 ETF 数据采集 (provider chain).

    单 symbol 内按 providers 顺序即时切换：首选失败立即试下一个，
    第一个成功即停止。所有 provider 都失败的 symbol 进 failed 列表。

    返回:
      out: 成功获取的 OHLC 数据
      fallback_map: {symbol: provider.name} 走了非首选 provider 的 symbol
      failed: 所有 provider 都失败的 symbol
    """
    out: dict[str, pd.DataFrame] = {}
    fallback_map: dict[str, str] = {}
    failed: list[str] = []
    codes: set[str] = set()
    for t in themes:
        for cn in t.cn_etfs:
            codes.add(cn.code)

    for code in sorted(codes):
        success_provider: EtfDataProvider | None = None
        for provider in providers:
            try:
                out[code] = provider.fetch_ohlc(code, lookback_days=400)
                success_provider = provider
                break
            except (ProviderError, EmptyDataError) as e:
                log.warning(f'CN fetch failed [{provider.name}] {code}: {e}')
                continue

        if success_provider is None:
            failed.append(code)
        elif success_provider is not providers[0]:
            fallback_map[code] = success_provider.name

        time.sleep(random.uniform(0.3, 1.0))  # jitter

    return out, fallback_map, failed
```

- [ ] **Step 4: 运行新测试验证全绿**

```bash
cd backend && uv run --all-extras pytest tests/test_pipeline_provider_chain.py -v 2>&1 | tail -15
```

期望：6 个测试全 PASS。

- [ ] **Step 5: 暂不提交**

`run_pipeline` 和 `compute_outputs` 的调用方仍是旧签名，跑全套测试会失败，留到 Task 7-8 后一起提交。

---

## Task 7: `compute_outputs` 接线 `cn_fallback_map`

**Files:**
- Modify: `backend/src/pipeline.py`
- Modify: `backend/tests/test_pipeline_compute_outputs.py`

- [ ] **Step 1: 修改 `backend/src/pipeline.py` 的 `compute_outputs` 签名**

第 154 行函数签名改为：

```python
def compute_outputs(
    themes: list[ThemeConfig],
    us_ohlc: dict[str, pd.DataFrame],
    cn_ohlc: dict[str, pd.DataFrame],
    us_failed: list[str],
    cn_failed: list[str],
    algo: AlgoConfig,
    asof_bjt: datetime,
    mode: PipelineMode,
    backfilled: bool = False,
    cn_fallback_map: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """...（保留原 docstring，加一行说明 cn_fallback_map）...

    cn_fallback_map: {symbol: provider_name} 走了非首选 provider 的 symbol。
        当 cn_fallback_map 非空且 cn_failed 为空时，cn provider status = 'fallback'。
    """
```

并在函数顶部初始化：

```python
if cn_fallback_map is None:
    cn_fallback_map = {}
```

- [ ] **Step 2: 改 `MetaInfo` 构造（约 376-391 行）**

```python
# 计算 cn provider status
if cn_failed:
    cn_status = 'degraded'
elif cn_fallback_map:
    cn_status = 'fallback'
else:
    cn_status = 'ok'

meta = MetaInfo(
    last_full_refresh=FullRefreshTimes(us=asof_bjt.isoformat(), cn=asof_bjt.isoformat()),
    last_intraday_refresh=asof_bjt.isoformat() if mode == PipelineMode.INTRADAY else None,
    providers={
        'us': ProviderInfo(status='ok' if not us_failed else 'degraded', name='yfinance'),
        'cn': ProviderInfo(status=cn_status, name='akshare-em'),
    },
    failed_symbols=us_failed + cn_failed,
    fallback_symbols=cn_fallback_map,
    stale_minutes=0,
    calendar=CalendarInfo(
        us_trading_today=is_us_trading_day(today_bjt),
        cn_trading_today=is_cn_trading_day(today_bjt),
        us_session_active=is_us_session_active(asof_utc),
        cn_session_active=is_cn_session_active(asof_bjt),
    ),
    backfilled=backfilled,
)
```

变更点：
- 替换原 `cn` ProviderInfo 内 `status='ok' if not cn_failed else 'degraded'` 为三态判定
- `name='akshare'` 改为 `name='akshare-em'`
- 新增 `fallback_symbols=cn_fallback_map`

- [ ] **Step 3: 修改 `backend/tests/test_pipeline_compute_outputs.py`**

定位调用 `compute_outputs(...)` 的位置，向调用补充关键字参数。新增至少一个测试用例验证三态：

```python
def test_compute_outputs_cn_fallback_status(...) -> None:
    """有 fallback 但无 failed → cn.status='fallback', fallback_symbols 非空"""
    # 用现有 fixture 生成 themes + us_ohlc + cn_ohlc
    # 调用 compute_outputs 时传 cn_failed=[], cn_fallback_map={'159755': 'akshare-sina'}
    # 断言 meta_json['providers']['cn']['status'] == 'fallback'
    # 断言 meta_json['fallback_symbols'] == {'159755': 'akshare-sina'}
```

具体实现要参考该文件已有的 fixture 模式（先读文件确认）。补一个测试名 `test_compute_outputs_cn_fallback_status`，断言三态判定矩阵的 fallback 行。

读取现有文件参考其他测试样式：
```bash
head -50 backend/tests/test_pipeline_compute_outputs.py
```

如果发现现有测试硬编码断言 `meta['providers']['cn']['name'] == 'akshare'`，将其改为 `'akshare-em'`。

- [ ] **Step 4: 运行 compute_outputs 测试验证三态**

```bash
cd backend && uv run --all-extras pytest tests/test_pipeline_compute_outputs.py -v 2>&1 | tail -20
```

期望：所有测试包括新的 `test_compute_outputs_cn_fallback_status` 都 PASS。

---

## Task 8: `run_pipeline` 注入 providers list

**Files:**
- Modify: `backend/src/pipeline.py`
- Modify: `backend/src/providers/__init__.py`
- Modify: `backend/tests/test_pipeline_smoke.py`

- [ ] **Step 1: 修改 `backend/src/providers/__init__.py`**

将文件内容设为：

```python
"""Provider 实现集合"""
from .akshare_em_provider import AkshareEmProvider
from .akshare_sina_provider import AkshareSinaProvider
from .base import EmptyDataError, EtfDataProvider, ProviderError
from .yfinance_provider import YfinanceProvider

__all__ = [
    'AkshareEmProvider',
    'AkshareSinaProvider',
    'EmptyDataError',
    'EtfDataProvider',
    'ProviderError',
    'YfinanceProvider',
]
```

- [ ] **Step 2: 修改 `backend/src/pipeline.py` 中 `run_pipeline`**

import 部分（约 47-49 行）改为：

```python
from .providers.akshare_em_provider import AkshareEmProvider
from .providers.akshare_sina_provider import AkshareSinaProvider
from .providers.base import EmptyDataError, EtfDataProvider, ProviderError
from .providers.yfinance_provider import YfinanceProvider
```

`run_pipeline` 中（约 407-416 行）改为：

```python
yf_provider = YfinanceProvider()
cn_providers: list[EtfDataProvider] = [
    AkshareEmProvider(),
    AkshareSinaProvider(),
]

us_ohlc, us_failed = _collect_us_ohlc(themes, yf_provider)
cn_ohlc, cn_fallback_map, cn_failed = _collect_cn_ohlc(themes, cn_providers)

now_utc = datetime.now(timezone.utc)
now_bjt = now_utc.astimezone(BJT)
themes_json, etfs_json, signals_json, meta_json = compute_outputs(
    themes, us_ohlc, cn_ohlc, us_failed, cn_failed, algo,
    asof_bjt=now_bjt, mode=mode, cn_fallback_map=cn_fallback_map,
)
```

变更点：
- `ak_provider = AkshareEmProvider()` → 改为 `cn_providers = [AkshareEmProvider(), AkshareSinaProvider()]`
- `_collect_cn_ohlc(themes, ak_provider)` → `_collect_cn_ohlc(themes, cn_providers)`，多接一个返回值 `cn_fallback_map`
- `compute_outputs(..., cn_fallback_map=cn_fallback_map)` 加 kwarg

- [ ] **Step 3: 修改 `backend/tests/test_pipeline_smoke.py`**

查找对 `_collect_cn_ohlc` 的引用，更新调用签名（接收 list）和解构（3 个返回值）。

如果 smoke 测试直接调用 `run_pipeline` 而不是 `_collect_cn_ohlc`，可能只需要 mock providers 集合，无需修改调用签名；先读文件确认：

```bash
grep -n "_collect_cn_ohlc\|AkshareProvider\|AkshareEmProvider\|run_pipeline\|cn_providers" backend/tests/test_pipeline_smoke.py
```

按 grep 结果作最小化适配（如：mock patch 路径从 `AkshareProvider` 改成 `AkshareEmProvider` 类名，如果还有 `ak_provider` 单例 mock 改成 list mock）。

- [ ] **Step 4: 运行所有 backend 测试**

```bash
cd backend && uv run --all-extras pytest 2>&1 | tail -20
```

期望：所有 backend 测试 PASS。如有 lint 警告但非测试失败可在 Step 5 提交后另行处理。

- [ ] **Step 5: 提交 Task 6 + 7 + 8**

```bash
git add backend/src/pipeline.py \
        backend/src/providers/__init__.py \
        backend/tests/test_pipeline_provider_chain.py \
        backend/tests/test_pipeline_compute_outputs.py \
        backend/tests/test_pipeline_smoke.py
git commit -m "feat(pipeline): introduce CN provider chain with immediate fallback"
```

---

## Task 9: 前端 schema 同步

**Files:**
- Modify: `frontend/src/types/meta.ts`
- Modify: `frontend/src/types/__tests__/schemas.test.ts`

- [ ] **Step 1: 修改 `frontend/src/types/meta.ts`**

```ts
import { z } from 'zod';

export const ProviderStatusSchema = z.enum(['ok', 'fallback', 'degraded', 'stale']);
export type ProviderStatus = z.infer<typeof ProviderStatusSchema>;

export const ProviderInfoSchema = z.object({
  status: ProviderStatusSchema,
  name: z.string(),
});
export type ProviderInfo = z.infer<typeof ProviderInfoSchema>;

export const MetaFileSchema = z.object({
  schema_version: z.string(),
  last_full_refresh: z.object({
    us: z.string().nullable(),
    cn: z.string().nullable(),
  }),
  last_intraday_refresh: z.string().nullable(),
  providers: z.object({
    us: ProviderInfoSchema,
    cn: ProviderInfoSchema,
  }),
  failed_symbols: z.array(z.string()),
  fallback_symbols: z.record(z.string(), z.string()).default({}),
  stale_minutes: z.number().int().nonnegative(),
  calendar: z.object({
    us_trading_today: z.boolean(),
    cn_trading_today: z.boolean(),
    us_session_active: z.boolean(),
    cn_session_active: z.boolean(),
  }),
});
export type MetaFile = z.infer<typeof MetaFileSchema>;
```

变更点：
- `ProviderStatusSchema` 加 `'fallback'`
- `MetaFileSchema` 增加 `fallback_symbols: z.record(z.string(), z.string()).default({})`

- [ ] **Step 2: 修改 `frontend/src/types/__tests__/schemas.test.ts`**

先读现有测试：

```bash
cat frontend/src/types/__tests__/schemas.test.ts | head -80
```

补充测试用例（追加到合适位置）：

```ts
import { describe, it, expect } from 'vitest';
import { MetaFileSchema, ProviderStatusSchema } from '../meta';

describe('ProviderStatusSchema', () => {
  it('accepts fallback status', () => {
    expect(() => ProviderStatusSchema.parse('fallback')).not.toThrow();
  });
});

describe('MetaFileSchema fallback_symbols', () => {
  const baseMeta = {
    schema_version: '1.1',
    last_full_refresh: { us: '2026-06-19T00:00:00+08:00', cn: '2026-06-19T00:00:00+08:00' },
    last_intraday_refresh: null,
    providers: {
      us: { status: 'ok', name: 'yfinance' },
      cn: { status: 'fallback', name: 'akshare-em' },
    },
    failed_symbols: [],
    stale_minutes: 0,
    calendar: { us_trading_today: true, cn_trading_today: true, us_session_active: false, cn_session_active: false },
  };

  it('parses meta with fallback_symbols map', () => {
    const m = MetaFileSchema.parse({ ...baseMeta, fallback_symbols: { '159755': 'akshare-sina' } });
    expect(m.fallback_symbols).toEqual({ '159755': 'akshare-sina' });
  });

  it('defaults fallback_symbols to {} when missing', () => {
    const m = MetaFileSchema.parse(baseMeta);
    expect(m.fallback_symbols).toEqual({});
  });
});
```

- [ ] **Step 3: 跑前端 schema 测试**

```bash
cd frontend && npx vitest run src/types/__tests__/schemas.test.ts 2>&1 | tail -15
```

期望：所有测试 PASS。

- [ ] **Step 4: 暂不提交**

等 Task 10-11 完成后一起提交前端改动。

---

## Task 10: `alert.tsx` 加 `warning` variant

**Files:**
- Modify: `frontend/src/components/ui/alert.tsx`

- [ ] **Step 1: 修改 `frontend/src/components/ui/alert.tsx`**

第 6-20 行 `alertVariants` 改为：

```tsx
const alertVariants = cva(
  "group/alert relative grid w-full gap-0.5 rounded-lg border px-2.5 py-2 text-left text-sm has-data-[slot=alert-action]:relative has-data-[slot=alert-action]:pr-18 has-[>svg]:grid-cols-[auto_1fr] has-[>svg]:gap-x-2 *:[svg]:row-span-2 *:[svg]:translate-y-0.5 *:[svg]:text-current *:[svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-card text-card-foreground",
        destructive:
          "bg-card text-destructive *:data-[slot=alert-description]:text-destructive/90 *:[svg]:text-current",
        warning:
          "bg-amber-50/50 border-amber-500/30 text-amber-700 *:data-[slot=alert-description]:text-amber-700/90 dark:bg-amber-900/20 dark:text-amber-300 dark:*:data-[slot=alert-description]:text-amber-300/90",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)
```

变更点：
- `variants.variant` 添加 `warning` 键，使用 amber 色调，与 destructive 红色明显区别

- [ ] **Step 2: 跑前端 build 验证 TypeScript 不报错**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

期望：无错误。

---

## Task 11: `StaleBanner` 三态实现 (TDD)

**Files:**
- Create: `frontend/src/components/Header/__tests__/StaleBanner.test.tsx`
- Modify: `frontend/src/components/Header/StaleBanner.tsx`

- [ ] **Step 1: 写失败测试 `frontend/src/components/Header/__tests__/StaleBanner.test.tsx`**

先看现有同目录其他测试以学习 DataContext mock 模式：

```bash
ls frontend/src/components/Header/__tests__/ 2>/dev/null
grep -rn "useDataContext\|DataContext" frontend/src/components/Header/__tests__/ 2>/dev/null | head -10
```

如果不存在 `__tests__/` 目录，需创建。

写测试（如果项目有 DataContext 测试帮手，复用之；否则用 vi.mock）：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StaleBanner } from '../StaleBanner';
import type { MetaFile } from '@/types/meta';

const mockMeta = vi.hoisted(() => ({ value: null as MetaFile | null }));

vi.mock('@/providers/dataContext', () => ({
  useDataContext: () => ({ meta: mockMeta.value }),
}));

const buildMeta = (overrides: Partial<MetaFile>): MetaFile => ({
  schema_version: '1.1',
  last_full_refresh: { us: '2026-06-19', cn: '2026-06-19' },
  last_intraday_refresh: null,
  providers: {
    us: { status: 'ok', name: 'yfinance' },
    cn: { status: 'ok', name: 'akshare-em' },
  },
  failed_symbols: [],
  fallback_symbols: {},
  stale_minutes: 0,
  calendar: { us_trading_today: true, cn_trading_today: true, us_session_active: false, cn_session_active: false },
  ...overrides,
});

describe('StaleBanner', () => {
  beforeEach(() => { mockMeta.value = null; });

  it('renders nothing when meta is null', () => {
    const { container } = render(<StaleBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when all ok', () => {
    mockMeta.value = buildMeta({});
    const { container } = render(<StaleBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('shows stale message when stale_minutes > 60 (highest priority)', () => {
    mockMeta.value = buildMeta({
      stale_minutes: 90,
      providers: { us: { status: 'ok', name: 'yfinance' }, cn: { status: 'degraded', name: 'akshare-em' } },
      failed_symbols: ['512000'],
    });
    render(<StaleBanner />);
    expect(screen.getByText(/已过期 90 分钟/)).toBeInTheDocument();
  });

  it('shows degraded message when any provider degraded', () => {
    mockMeta.value = buildMeta({
      providers: { us: { status: 'ok', name: 'yfinance' }, cn: { status: 'degraded', name: 'akshare-em' } },
      failed_symbols: ['512000', '159755'],
    });
    render(<StaleBanner />);
    expect(screen.getByText(/Provider 降级/)).toBeInTheDocument();
    expect(screen.getByText(/512000, 159755/)).toBeInTheDocument();
  });

  it('shows fallback message when any provider fallback', () => {
    mockMeta.value = buildMeta({
      providers: { us: { status: 'ok', name: 'yfinance' }, cn: { status: 'fallback', name: 'akshare-em' } },
      fallback_symbols: { '159755': 'akshare-sina', '588000': 'akshare-sina' },
    });
    render(<StaleBanner />);
    expect(screen.getByText(/2 个 ETF 使用备用数据源/)).toBeInTheDocument();
  });

  it('prioritizes degraded over fallback', () => {
    mockMeta.value = buildMeta({
      providers: { us: { status: 'ok', name: 'yfinance' }, cn: { status: 'degraded', name: 'akshare-em' } },
      failed_symbols: ['512000'],
      fallback_symbols: { '159755': 'akshare-sina' },
    });
    render(<StaleBanner />);
    expect(screen.getByText(/Provider 降级/)).toBeInTheDocument();
    expect(screen.queryByText(/使用备用数据源/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行测试验证全部失败**

```bash
cd frontend && npx vitest run src/components/Header/__tests__/StaleBanner.test.tsx 2>&1 | tail -20
```

期望：fallback 相关测试 FAIL（当前组件只有两态）。

- [ ] **Step 3: 修改 `frontend/src/components/Header/StaleBanner.tsx`**

```tsx
import { useDataContext } from '@/providers/dataContext';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const StaleBanner = () => {
  const { meta } = useDataContext();
  if (!meta) return null;

  const stale = meta.stale_minutes > 60;
  const degraded =
    meta.providers.us.status === 'degraded' ||
    meta.providers.cn.status === 'degraded';
  const fallback =
    meta.providers.us.status === 'fallback' ||
    meta.providers.cn.status === 'fallback';

  if (!stale && !degraded && !fallback) return null;

  if (stale) {
    return (
      <Alert variant="destructive" className="mt-2">
        <AlertDescription>数据获取异常 — 已过期 {meta.stale_minutes} 分钟</AlertDescription>
      </Alert>
    );
  }

  if (degraded) {
    return (
      <Alert variant="destructive" className="mt-2">
        <AlertDescription>Provider 降级: {meta.failed_symbols.join(', ')}</AlertDescription>
      </Alert>
    );
  }

  const fallbackCount = Object.keys(meta.fallback_symbols).length;
  return (
    <Alert variant="warning" className="mt-2">
      <AlertDescription>{fallbackCount} 个 ETF 使用备用数据源</AlertDescription>
    </Alert>
  );
};
```

- [ ] **Step 4: 跑测试验证全绿**

```bash
cd frontend && npx vitest run src/components/Header/__tests__/StaleBanner.test.tsx 2>&1 | tail -20
```

期望：6 个测试全 PASS。

- [ ] **Step 5: 跑全部前端测试，确认未回归**

```bash
cd frontend && npx vitest run 2>&1 | tail -10
```

期望：所有测试 PASS。

- [ ] **Step 6: 提交前端改动（Task 9 + 10 + 11）**

```bash
git add frontend/src/types/meta.ts \
        frontend/src/types/__tests__/schemas.test.ts \
        frontend/src/components/ui/alert.tsx \
        frontend/src/components/Header/StaleBanner.tsx \
        frontend/src/components/Header/__tests__/StaleBanner.test.tsx
git commit -m "feat(ui): add fallback variant to StaleBanner with warning alert"
```

---

## Task 12: 集成验证 + 文档收尾

**Files:**
- 无新建/修改源码；仅运行端到端检查

- [ ] **Step 1: 本地跑一次完整 pipeline 冒烟**

```bash
cd backend && uv run --all-extras python -m src.pipeline --mode intraday 2>&1 | tail -30
```

期望：pipeline 完成，`data/latest/meta.json` 含 `fallback_symbols` 字段。

- [ ] **Step 2: 检查 `data/latest/meta.json` 结构**

```bash
cd /Users/dreambt/sources/etf-radar && python3 -c "
import json
m = json.load(open('data/latest/meta.json'))
print('schema_version:', m['schema_version'])
print('cn.status:', m['providers']['cn']['status'])
print('cn.name:', m['providers']['cn']['name'])
print('fallback_symbols:', m.get('fallback_symbols', 'MISSING'))
print('failed_symbols:', m.get('failed_symbols'))
"
```

期望：
- `schema_version: 1.1`
- `cn.name: akshare-em`
- `fallback_symbols` 存在（dict）
- `cn.status` 是 `ok` / `fallback` / `degraded` 之一

- [ ] **Step 3: 启动前端 dev server，肉眼验证 StaleBanner 显示**

```bash
cd frontend && npm run dev 2>&1 | head -5 &
sleep 3
echo "frontend started, open http://localhost:5173 to verify StaleBanner"
```

人肉验证：
- 如果当前 meta.json 是 fallback 状态，应看到橙色"N 个 ETF 使用备用数据源"
- 如果是 ok 状态，应无 banner
- 关闭 dev server

- [ ] **Step 4: 检查全部测试 + lint**

```bash
cd backend && uv run --all-extras pytest 2>&1 | tail -10
cd ../frontend && npx vitest run 2>&1 | tail -10
cd ../frontend && npx eslint src 2>&1 | tail -10
cd ../backend && uv run --all-extras ruff check src tests 2>&1 | tail -10
```

期望：全部通过，无 lint 错误。

- [ ] **Step 5: 提交 spec doc（如尚未提交）**

```bash
cd /Users/dreambt/sources/etf-radar
git diff --staged --name-only | grep -q spec || git add docs/superpowers/specs/2026-06-19-cn-provider-chain-design.md
git diff --staged --quiet || git commit -m "docs(providers): add CN provider chain design spec"
```

- [ ] **Step 6: （可选）提交本 plan 文档**

```bash
git add docs/superpowers/plans/2026-06-19-cn-provider-chain.md
git commit -m "docs(providers): add CN provider chain implementation plan"
```

- [ ] **Step 7: 创建 PR（可选，等用户授权）**

不主动 push 或开 PR；待用户明确指示。

---

## Self-Review

**Spec 覆盖检查：**

| Spec 段落 | 对应 Task |
|---|---|
| §3.1 模块结构 | Task 1, 2, 8 |
| §3.3 算法 | Task 6 |
| §3.4 status 判定矩阵 | Task 7 |
| §3.5 provider 规格 (`_to_sina_symbol`, `standardize_ohlc` 扩展) | Task 2, 3 |
| §4.1 Backend Schema (`ProviderStatus`, `MetaInfo.fallback_symbols`) | Task 4 |
| §4.2 Frontend Schema | Task 9 |
| §4.3 JSON Schema | Task 5 |
| §5.1 StaleBanner 三态优先级 | Task 11 |
| §5.2 `warning` variant | Task 10 |
| §6.1 Backend 测试 | Task 1-7 |
| §6.2 Frontend 测试 | Task 9, 11 |
| §6.3 集成验证 | Task 12 |
| §8 实施顺序 | Task 1→12 顺序 |
| §9 Out of Scope (历史 schema 不一致) | 未触碰，符合 |

**类型/函数签名一致性检查：**

- `_collect_cn_ohlc(themes, providers)` 返回 `tuple[dict, dict[str, str], list[str]]` — Task 6 实现 + Task 8 调用 + 测试断言一致 ✓
- `compute_outputs(..., cn_fallback_map=...)` kwarg 默认 None — Task 7 签名 + Task 8 调用一致 ✓
- `MetaInfo.fallback_symbols: dict[str, str]` — Task 4 定义 + Task 7 填充 + Task 9 前端 zod ✓
- `AkshareEmProvider.name = 'akshare-em'` / `AkshareSinaProvider.name = 'akshare-sina'` — Task 1, 2 一致，Task 6 chain 算法依赖 provider.name 写入 fallback_map ✓
- `Alert variant='warning'` — Task 10 定义 + Task 11 使用一致 ✓

**Placeholder 扫描：**

- 无 TBD/TODO
- Task 7 Step 3 引导读现有文件再补测试 — 但已给出测试名 + 断言要点，不算 placeholder
- Task 8 Step 3 引导按 grep 结果适配 — 给出明确 grep 命令 + 改造方向，不算 placeholder
- Task 11 Step 1 引导确认 DataContext mock 模式 — 已给完整 mock 代码作 fallback，不算 placeholder

**Scope 确认：** 单 spec 单一目标（CN provider chain），12 个 task，预计 4-6 小时工作量。规模合适，无需拆分。
