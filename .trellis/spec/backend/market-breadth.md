# 市场宽度 / 温度链(market_breadth)

自建个股宽度(MA20/60/120)+ dapanyuntu 对账,产出市场温度页数据。核心模块:`src/market_breadth/self_breadth.py`(主展示)、`reconcile.py`(QC 对账)、`pipeline.py`(dapanyuntu 源)。

> 本文聚焦**输出契约与新鲜度信号**(C3)。健康哨兵如何消费这些信号见 `health-monitoring.md`。

---

## 1. Scope / Trigger
- 触发 code-spec 深度:跨层输出契约变更 —— `market_temperature.json` / `market_breadth_qc.json` 新增字段,被前端(温度页)与 health-monitor(C1)消费。

## 2. Signatures
```python
# src/market_breadth/self_breadth.py
def _expected_breadth_asof(now_bjt: datetime) -> date
#   期望"最近已收盘 CN 交易日":交易日且 ≥18:00(CN_SETTLE_HOUR)→ 今日;
#   否则回溯最近已收盘交易日(最多回溯 _ASOF_LOOKBACK_DAYS=21 天,覆盖春节+相邻周末)。
#   注意:与 pipeline._expected_cn_date 语义不同(见下「命名约定」),故独立命名。
def _freshness(dates: list[str], now_bjt: datetime) -> dict
#   → {as_of: str|None, expected_date: str, stale: bool};stale = as_of < expected
def compute_self_breadth(..., now_bjt: datetime | None = None) -> dict
def run(data_root: Path, now_bjt: datetime | None = None) -> Path

# src/market_breadth/reconcile.py
def reconcile(self_snapshot: dict, dapanyuntu_snapshot: dict, threshold: float = 5.0) -> dict
```

## 3. Contracts

### `market_temperature.json`(self_breadth 产出)—— 新增新鲜度字段
| 字段 | 类型 | 含义 |
|---|---|---|
| `as_of` | `str \| None` | 数据实际截至日(=`dates[-1]`);空序列为 None |
| `expected_date` | `str` | 期望的最近已收盘交易日(ISO) |
| `stale` | `bool` | `as_of < expected_date` 即陈旧;**不阻断出图**,仅标记 |
- 向后兼容:附加字段;前端 `marketTemperature.ts::V2Schema` 用 `.passthrough()`,未知字段安全忽略,无需改 zod。

### `market_breadth_qc.json`(reconcile 产出)—— 新增 `self_stale`
| 字段 | 类型 | 含义 |
|---|---|---|
| `self_stale` | `bool` | self 与 dpyt 均有点位且 `self.date < dapanyuntu.date` → True |
- `over_threshold` 语义不变(rate 偏差超阈);`self_stale` 用于区分"方法学微差"与"真陈旧"(self as-of 落后)。

### 日志前缀(C1 哨兵消费契约,勿随意改名)
- `temperature_stale: as_of=%s expected=%s` —— self_breadth.run 陈旧时 `log.warning`
- `reconcile_self_stale: self=%s dpyt=%s` —— reconcile self_stale 时 `log.warning`

## 4. Validation & Error Matrix
| 条件 | 行为 |
|---|---|
| 盘中(未到 18:00 结算) | expected 放宽为上一已收盘交易日 → **不误报 stale** |
| 非交易日(周末/假期) | 同上回溯,不误报 |
| `dates` 为空 | `as_of=None`、`stale=False`,不误报 |
| 回溯 21 天仍无交易日(超长假 / chinese_calendar 无该年数据) | 兜底返回 `today - 21`(窗口内最旧候选),**非** `today`;方向保守使 stale 倾向 False —— 避免春节等长假把"休市"误判成"数据陈旧"报假警 |
| reconcile 缺 self 或 dpyt 点位 | `self_stale=False`,不误判 |

## 5. Good/Base/Bad Cases
- Good:close_series 末日=期望交易日 → `stale=false`、`self_stale=false`,正常出图。
- Base:close_series 停在 T-1(如今日 backfill 未补)→ `stale=true` + `temperature_stale:` 日志;reconcile `self_stale=true`;图仍出但带标记,哨兵据此补偿。
- Bad(防回归):盘中 14:00 未到结算,末日=昨日 → **不得**判 stale(expected=昨日)。

## 6. Tests Required(assertion points)
- `test_self_breadth.py`:末日<期望→stale=true+as_of;末日==期望→false;盘中不误报;非交易日回溯;compute 输出携带三字段。
- `test_reconcile.py`:self.date<dpyt→self_stale=true;相等→false;缺点位→false。

## 7. 命名约定(Gotcha)
> **Warning**:`self_breadth._expected_breadth_asof` 与 `pipeline._expected_cn_date` **不可同名**。
>
> 二者语义相反:`pipeline._expected_cn_date` 盘中/非交易日返回 `None`(拿到啥用啥,不判陈旧);`_expected_breadth_asof` 必须返回一个基准日(回溯最近已收盘)才能判 stale。历史上曾同名 → 维护陷阱,已显式区分命名。新增"期望交易日"类函数前,先确认语义与既有函数是否冲突。

---

## 交界
- 生产者(本文)↔ 消费者(`health-monitoring.md`):`market_temperature.stale/as_of`、`qc.self_stale`、日志前缀。
- 根因:close_series 陈旧的修复在 C4(stocks-daily 补缺);本链只保证"陈旧不静默"。
