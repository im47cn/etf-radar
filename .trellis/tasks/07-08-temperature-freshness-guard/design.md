# C3 设计 · 温度链新鲜度护栏

## 变更清单

### 1. `market_breadth/self_breadth.py`
- 新增新鲜度判定(纯函数,易测):
```
def _freshness(dates: list[str], now_bjt: datetime) -> dict:
    """返回 {as_of, expected_date, stale}。
    expected = 期望 CN 交易日(收盘后为今日, 盘中/非交易日为最近已收盘交易日或 None)。
    stale = as_of < expected(且 expected 可判)。"""
```
  - 复用 `etl/calendar.is_cn_trading_day`;"最近已收盘交易日"逻辑参照 `pipeline._expected_cn_date` 语义(交易日 & ≥结算时=今日)。盘中/未到结算 → expected 放宽为上一交易日,避免误报。
- `compute_self_breadth` 输出新增字段:`as_of`(=dates[-1])、`stale`(bool)、`expected_date`。保持 schema 向后兼容(新增可选字段,前端忽略即可)。
- `run()` 中若 `stale` → `log.warning('temperature_stale: as_of=%s expected=%s', ...)`(结构化前缀供 C1)。
- **不阻断**:仍写出 market_temperature.json(带 stale 标记)。

### 2. `market_breadth/reconcile.py`
- `reconcile()` 增 `self_stale`:当 `s`(self)与 `d`(dpyt)均有且 `s[0] < d[0]`(self as-of 早于 dpyt)→ `self_stale=True`。
- qc.json 输出新增 `self_stale` 字段;`over_threshold` 语义不变。
- 日志:`self_stale` 时 `log.warning('reconcile_self_stale: self=%s dpyt=%s', s[0], d[0])`。

## 数据流
```
close_series(可能陈旧) → self_breadth
   → _freshness → market_temperature.json{as_of, stale, expected_date}
   → (stale) log.warning temperature_stale
reconcile(self vs dpyt)
   → qc.json{over_threshold, self_stale}
   → (self_stale) log.warning reconcile_self_stale
C1 哨兵读 market_temperature.stale / qc.self_stale → 触发补偿(stocks-daily/backfill + cn-refresh 重算) + 告警
```

## 为什么"标记不阻断"
- 阻断出图会让温度页整块空白,体验更差;标记 + 前端"截至X日" + C1 自愈补齐,兼顾可用与真实。
- 与 C2 一致哲学:暴露真实状态,让上层(前端/哨兵)决策,而非静默或粗暴阻断。

## 兼容 / 风险
- market_temperature.json 新增字段:前端 zod schema 若 strict 需同步(检查 `types/` 是否 strict;新增可选字段一般兼容)。实现时验证前端不因未知字段报错。
- reconcile 已有测试需补 `self_stale` 断言,注意不破坏现有断言。
- 盘中误报:expected 放宽为上一交易日规避。

## 回滚点
- self_breadth 与 reconcile 改动独立,可分别 revert。新增字段为附加,回滚不影响既有消费。

## 交界
- 输出字段(market_temperature.stale/as_of、qc.self_stale)+ 日志前缀(temperature_stale / reconcile_self_stale)= C1 消费契约。
- 与 C4:close_series 陈旧的**根因修复**在 C4(补缺);C3 只负责"陈旧时不静默"。
