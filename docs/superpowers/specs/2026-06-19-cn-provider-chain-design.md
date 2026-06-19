# CN ETF Provider Chain 设计

**日期**: 2026-06-19
**作者**: brainstorm session
**状态**: Draft, 待审阅
**关联**: 失败模式分析见 `data/latest/meta.json` + GitHub Actions runs `27746631337`, `27737481817`

## 1. 背景与动机

### 1.1 现象

最近 24 小时内多次 CN Refresh GitHub Actions 运行结果：

| Run ID | 时间 (BJT) | failed | recovered (second-pass) |
|---|---|---|---|
| 27732650597 | 10:27 | 0 | n/a |
| 27733853897 | 11:05 | 0 | 4/4 |
| 27737481817 | 12:59 | **23** | **0/23** |
| 27741424738 | 14:36 | 0 | n/a |
| 27746631337 | 16:32 | **23** | **0/23** |

`data/latest/meta.json` 因此显示 `cn.status='degraded'`, `failed_symbols` 列出固定的 23 个 A 股 ETF。前端 `StaleBanner` 将此呈现为醒目的"Provider 降级"红色警告。

### 1.2 根因

1. **错误信号**: 全部 23 个失败的根因均为同一异常：
   `('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`
2. **触发模式**: 失败 symbol 集合**固定**（159755, 162411, 512000, 515030, ...），非随机抖动 — 对端服务端对特定 symbol 段稳定拒绝。
3. **重试策略不足**: `AkshareProvider` 内部 3 次指数退避 (2/4/8s) + 60s second-pass 同源重试，无法穿透对端持久故障。
4. **单点依赖**: `pipeline.py:407-411` 仅 `AkshareProvider` (东方财富 EM 源) 一个 A 股 provider，没有真正的 fallback。

### 1.3 目标

- 引入**可扩展的 provider chain** 机制（不仅满足当前 2 个 provider，预留未来 N 个）
- 当主源 EM 失败时，自动 fallback 到备用源 sina，避免醒目降级警告
- meta 显式区分三态 `ok` / `fallback` / `degraded`，可观测哪些 symbol 来自哪个源
- 前端区别展示，fallback 用柔和的提示，仅"双源全失败"时显示醒目降级

### 1.4 非目标

- 不修改 US (yfinance) 数据源策略（独立工作）
- 不引入持久化 OHLC cache（C 方案，留作后续迭代）
- 不修正前端 schema 已有的历史不一致（`'stale'` 状态、`backfilled` 字段，需要独立 PR）
- 不引入 i18n 框架（保持现有简体中文硬编码）

## 2. 可行性验证

通过本地脚本验证 `akshare.fund_etf_hist_sina` 对失败的 3 个 symbol：

```text
OK 159755 -> sina sz159755: rows=1208, cols=['date','open','high','low','close','volume','amount']
OK 512000 -> sina sh512000: rows=2366, last_date=2026-06-18
OK 588000 -> sina sh588000: rows=1355, last_date=2026-06-18
```

**结论**: sina 源能拿到失败 symbol 的完整数据，含最新交易日。

**关键差异**:

| 项 | EM (`fund_etf_hist_em`) | Sina (`fund_etf_hist_sina`) |
|---|---|---|
| 复权 | 支持 `adjust='qfq'`（前复权）| **无复权参数**（返回不复权价）|
| symbol 格式 | `159755` | 需 `sh`/`sz` 前缀 |
| 列名 | 中文 + 涨跌幅 | 英文：date/open/high/low/close/volume/amount |
| 时间范围 | start/end 可指定 | 全历史 |

设计决策：**接受 sina 不复权差异**（思路 A）。理由：
- sina 仅作兜底，频次低
- ETF 分红/拆分远少于股票，对 mapping_score（窗口 60-120 天）和 returns（21-126 天）的影响在可接受范围
- meta 显式记录 fallback symbol，便于事后核对

## 3. 架构设计

### 3.1 模块结构

```
backend/src/providers/
  ├── base.py                       # EtfDataProvider 接口不变
  ├── akshare_em_provider.py        # 原 akshare_provider.py 改名，name="akshare-em"
  ├── akshare_sina_provider.py      # 新增, name="akshare-sina"
  └── __init__.py                   # 导出公开 API

backend/src/pipeline.py
  └── _collect_cn_ohlc(themes, providers: list[EtfDataProvider])
      # providers 顺序 = chain 优先级（providers[0] 为主源）
      # 返回: (ohlc_dict, fallback_map, failed_symbols)

backend/src/models.py
  └── ProviderStatus: Literal['ok','fallback','degraded']
  └── MetaInfo.fallback_symbols: dict[str, str]
```

**核心设计原则**: chain 逻辑放在 pipeline 层，保持 `EtfDataProvider` 接口纯净；各 provider 独立可测。

### 3.2 数据流

```
run_pipeline()
   ├─ load_themes/algo
   ├─ providers = [AkshareEmProvider(), AkshareSinaProvider()]   # 硬编码顺序
   ├─ us_ohlc, us_failed = _collect_us_ohlc(themes, yf_provider)
   ├─ cn_ohlc, cn_fallback_map, cn_failed = _collect_cn_ohlc(themes, providers)
   ├─ compute_outputs(..., cn_fallback_map=cn_fallback_map, ...)
   │    └─ MetaInfo:
   │         providers.cn.status = ok | fallback | degraded
   │         fallback_symbols = cn_fallback_map
   │         failed_symbols = us_failed + cn_failed
   └─ atomic_write_json(...)
```

### 3.3 `_collect_cn_ohlc` 算法

```python
def _collect_cn_ohlc(
    themes: list[ThemeConfig],
    providers: list[EtfDataProvider],
) -> tuple[dict[str, pd.DataFrame], dict[str, str], list[str]]:
    """
    返回:
      ohlc: 成功获取的 OHLC 数据
      fallback_map: {symbol: provider.name} 走了非首选 provider 的 symbol
      failed: 所有 provider 都失败的 symbol
    """
    codes = sorted({cn.code for t in themes for cn in t.cn_etfs})
    ohlc, fallback_map, failed = {}, {}, []

    for code in codes:
        success_provider: EtfDataProvider | None = None
        for provider in providers:
            try:
                ohlc[code] = provider.fetch_ohlc(code, lookback_days=400)
                success_provider = provider
                break
            except (ProviderError, EmptyDataError) as e:
                log.warning(f'CN fetch failed [{provider.name}] {code}: {e}')
                continue

        if success_provider is None:
            failed.append(code)
        elif success_provider is not providers[0]:
            fallback_map[code] = success_provider.name

        time.sleep(random.uniform(0.3, 1.0))   # jitter, 避免对端限流

    return ohlc, fallback_map, failed
```

**关键设计点**:
- **即时切换（策略 3）**：单 symbol 内 EM 失败立即试 sina；移除原 60s second-pass（每个 provider 内部已有 3 次指数退避）
- **provider 顺序硬编码**：`providers=[em, sina]`，未来加 provider 改 1 行
- **jitter 保留**：避免对端按 symbol 段限流

### 3.4 status 判定矩阵

| fallback_symbols | failed_symbols | cn.status |
|---|---|---|
| ∅ | ∅ | `ok` |
| 非空 | ∅ | `fallback` |
| 任意 | 非空 | `degraded` |

### 3.5 provider 实现规格

**AkshareSinaProvider**:

```python
class AkshareSinaProvider(EtfDataProvider):
    name = 'akshare-sina'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0) -> None:
        ...

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        sina_symbol = self._to_sina_symbol(symbol)   # 159xxx→sz, 5xxxxx/6xxxxx→sh
        for attempt in range(self.max_retries):
            try:
                df = ak.fund_etf_hist_sina(symbol=sina_symbol)
                if df is None or df.empty:
                    raise EmptyDataError(f'sina empty for {symbol}')
                df_recent = df.tail(int(lookback_days * 1.6))   # 截取近 N 天
                return standardize_ohlc(df_recent, source='akshare-sina')
            except EmptyDataError:
                raise
            except Exception as e:
                last_exc = e
                log.warning(f'sina attempt {attempt+1} failed for {symbol}: {e}')
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        raise ProviderError(f'sina failed after {self.max_retries} retries: {last_exc}')

    @staticmethod
    def _to_sina_symbol(em_symbol: str) -> str:
        """159xxx → sz159xxx; 5xxxxx/6xxxxx → sh{symbol}."""
        if em_symbol.startswith('1'):   # 深市 ETF: 159xxx, 162xxx
            return f'sz{em_symbol}'
        if em_symbol.startswith(('5', '6')):   # 沪市 ETF: 5xxxxx, 6xxxxx
            return f'sh{em_symbol}'
        raise ValueError(f'unknown CN ETF symbol prefix: {em_symbol}')
```

**`standardize_ohlc(df, source)` 扩展**:
- 新增 `source='akshare-sina'` 分支
- 输入列: `date, open, high, low, close, volume, amount` (英文)
- 输出: 与 EM 一致的标准 OHLC DataFrame

## 4. Schema 变更

### 4.1 Backend (`backend/src/models.py`)

```python
class ProviderStatus(str, Enum):
    OK = 'ok'
    FALLBACK = 'fallback'   # 新增
    DEGRADED = 'degraded'

class ProviderInfo(BaseModel):
    status: ProviderStatus
    name: str                # chain 第一个 provider 的 name

class MetaInfo(BaseModel):
    schema_version: str = '1.1'   # 1.0 → 1.1
    ...
    failed_symbols: list[str]
    fallback_symbols: dict[str, str] = Field(default_factory=dict)   # 新增
    ...
```

### 4.2 Frontend (`frontend/src/types/meta.ts`)

```ts
export const ProviderStatusSchema = z.enum(['ok', 'fallback', 'degraded', 'stale']);

export const MetaFileSchema = z.object({
  ...,
  fallback_symbols: z.record(z.string(), z.string()).default({}),
});
```

向前兼容：旧 meta.json（无 `fallback_symbols`）解析为 `{}`。

### 4.3 JSON Schema (`backend/tests/schemas/meta.schema.json`)

同步更新校验规则。

## 5. 前端展示

### 5.1 `StaleBanner` 三态优先级

| 判定（高→低优先级） | variant | 文案 |
|---|---|---|
| `stale_minutes > 60` | `destructive` 红 | 数据获取异常 — 已过期 N 分钟 |
| 任一 provider `status='degraded'` | `destructive` 红 | Provider 降级: {failed_symbols 列表} |
| 任一 provider `status='fallback'` | `warning` 橙（新增） | N 个 ETF 使用备用数据源 |
| 全 ok | 不显示 | - |

实现：
```tsx
const { meta } = useDataContext();
if (!meta) return null;
const stale = meta.stale_minutes > 60;
const degraded = meta.providers.us.status === 'degraded' || meta.providers.cn.status === 'degraded';
const fallback = meta.providers.us.status === 'fallback' || meta.providers.cn.status === 'fallback';
if (!stale && !degraded && !fallback) return null;

if (stale)     return <Alert variant="destructive">数据获取异常 — 已过期 {meta.stale_minutes} 分钟</Alert>;
if (degraded)  return <Alert variant="destructive">Provider 降级: {meta.failed_symbols.join(', ')}</Alert>;
return <Alert variant="warning">{Object.keys(meta.fallback_symbols).length} 个 ETF 使用备用数据源</Alert>;
```

### 5.2 `ui/alert` 新增 `warning` variant

```css
warning: border-amber-500/30 bg-amber-50/50 text-amber-700
         dark: bg-amber-900/20 text-amber-300
```

色调：暖色调，与 `destructive` 红色明显区别，不刺眼。

## 6. 测试策略

### 6.1 Backend 新增/修改

| 文件 | 类型 | 覆盖点 |
|---|---|---|
| `tests/test_akshare_sina_provider.py` | 新增 | ① symbol 前缀映射（512xxx→sh, 159xxx→sz, 588xxx→sh, 异常前缀 raise）② 空数据→EmptyDataError ③ 异常→重试→ProviderError ④ schema 标准化为统一 OHLC |
| `tests/test_pipeline_provider_chain.py` | 新增 | ① 全主源成功→`status=ok`, `fallback_symbols={}` ② 部分主源失败、sina 接力→`status=fallback`, `fallback_symbols` 正确映射 ③ 双源全失败→`status=degraded`, `failed_symbols` 含该 symbol ④ 单 symbol 即时切换（验证调用顺序）|
| `tests/test_pipeline_smoke.py` | 修改 | 适配 `_collect_cn_ohlc` 新签名（接收 `providers: list[EtfDataProvider]`）|
| `tests/test_akshare_provider.py` | 修改 | 类重命名 `AkshareProvider` → `AkshareEmProvider` |
| `tests/schemas/meta.schema.json` | 修改 | 新 status 枚举值 + fallback_symbols 字段 |

### 6.2 Frontend 新增/修改

| 文件 | 类型 | 覆盖点 |
|---|---|---|
| `__tests__/StaleBanner.test.tsx` | 新增 | 三态文案 + 优先级（stale > degraded > fallback > ok）|
| `types/__tests__/schemas.test.ts` | 修改 | 解析含 `fallback_symbols` 的 meta；`'fallback'` status 通过校验；旧 meta（无 fallback_symbols）默认为 `{}` |

### 6.3 集成验证

实施完成后，本地手动跑一次完整 pipeline，模拟 EM 部分失败，验证：
- meta.json 中 `cn.status='fallback'`，`fallback_symbols` 非空
- 前端 StaleBanner 显示橙色 "N 个 ETF 使用备用数据源"
- 失败 symbol 的 returns/strength 在 etfs.json 中正常输出

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| sina 也临时断 → 全 fallback 失败 | provider 内部保留 3 次指数退避；记录到 failed_symbols 进入 degraded 状态（设计已覆盖）|
| sina 返回不复权 → mapping_score 略漂移 | 接受（思路 A）；fallback_symbols 显式记录，便于事后核对 |
| meta schema 变更破坏前端旧版本 | `fallback_symbols` 设默认值 `{}`；ProviderStatus 加值不删值；schema_version 1.0→1.1 |
| `AkshareProvider` 重命名破坏现有引用 | 用 git grep 找全部引用，一次性替换；保留旧名作 alias 1 个版本（可选）|
| 单 symbol 即时切换导致 sina 突发压力（EM 整体抖动时 23 symbol 立即打 sina）| jitter 保留；sina 内部 3 次指数退避；若仍有问题，未来可加 batch delay 配置 |
| 不复权 + 复权数据混算导致历史回测异常 | scope 内不处理；future work 中加入持久化 OHLC cache 后可分离回测/实时路径 |

## 8. 实施顺序

1. **TDD 起步**: 先写 `test_akshare_sina_provider.py`（红）→ 实现 `AkshareSinaProvider`（绿）
2. **重命名**: `AkshareProvider` → `AkshareEmProvider`，更新引用与测试
3. **pipeline 改造**: 改 `_collect_cn_ohlc` 签名 + 算法，写 `test_pipeline_provider_chain.py`
4. **models 扩展**: `ProviderStatus` 加 `FALLBACK`、`MetaInfo` 加 `fallback_symbols`
5. **compute_outputs 接线**: 接收 `fallback_map`，按矩阵填 status
6. **前端 schema**: 同步 `meta.ts` + `schemas.test.ts`
7. **前端 StaleBanner**: 三态实现 + `warning` variant + 测试
8. **集成验证**: 本地手动跑一次 + 模拟 EM 部分失败

## 9. Out of Scope（明确不做）

- 持久化 OHLC cache（C 方案）
- US provider 改造
- 修正前端 schema 历史不一致（`'stale'` 未在 backend、`backfilled` 未在前端）
- 第三个备用源（如 baostock、tushare）
- 前端 fallback symbol 详细列表展示（仅显示 N 个数量，详细列表可在 dev tools 查 meta.json）
- algo.yml 配置 provider chain 顺序
