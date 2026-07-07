# Research: 附加 — 变化计算所需 snapshot 的可得性

- **Query**: `data/snapshots/<date>/` 每日是否稳定含 themes.json / etfs.json / market_temperature.json（供今日 vs 昨日 diff）？
- **Scope**: internal
- **Date**: 2026-07-07

## 结论（一句话）

`themes.json` / `etfs.json` **100% 稳定每日产出**（A/D 依赖成立）；`market_temperature.json` **不稳定**（约 2026-07-03 才上线，此前普遍缺失），因此 **C 必须对 mt 缺失安全降级**。

## 证据

抽查近 30 个 snapshot 目录（`data/snapshots/`，2026-05-26 .. 2026-07-07）：

| 文件 | 缺失天数 | 说明 |
|---|---|---|
| `themes.json` | 0 / 30 | 全齐，含 `strength{short,mid,long,composite}` |
| `etfs.json` | 0 / 30 | 全齐，含 `strength{...}`、`theme_id`、`theme_ids[]` |
| `market_temperature.json` | 27 / 30 | 仅 07-03/07-06/07-07 有；功能新上线 |

字段抽验（有 mt 的天）：
- `themes.json`：30 主题，composite 全部有值（30/30）。
- `etfs.json`：41 ETF。
- `market_temperature.json → periods.ma20.market` 末值：07-07 文件为 `{date:'2026-07-06', rate:37.5}`。
  - **注意：mt 的 `market` 序列 latest 落后文件日期约 1 交易日**（07-07 归档里最新 rate 是 07-06），diff 时以序列内 `date` 对齐，而非 snapshot 目录名。

数据结构参考：
- themes：`themes[].{id,name,strength{short,mid,long,composite},rank,tags,...}`
- etfs：`etfs[].{code,name,theme_id,theme_ids[],strength{...}}`
- mt：`periods.{ma20,ma60,ma120}.{market[],industries_l1[],industries_l2[]}`

## 对 design / implement 的影响

1. **A（象限迁移）/ D（composite 跨 50）**：依赖 themes/etfs，数据稳定，可放心实现「今日 vs 昨日」diff。
2. **C（全市场温度档切换）**：依赖 mt——昨日 mt 常缺（历史普遍，未来若管线故障也可能缺）。实现须：昨日或今日 mt 缺失 → **跳过 C，不报错**（符合 prd「昨日 snapshot 不存在时安全降级」）。
3. **prev-day 解析**：不能简单「目录名 -1 天」，需按交易日/实际存在的目录回溯上一份 snapshot；且 mt diff 应基于序列内 `date` 字段对齐，规避 latest 落后一日的偏移。

## Caveats / Not Found

- 未定位现成的「上一交易日 snapshot 解析」工具函数；实现时需确认 `data/snapshots` 是否只含交易日（周末/节假日无目录）以正确取「昨日」。
- mt 覆盖率未来会随功能稳定提升，但历史 backfill 不会补齐——回看/首次上线期 C 触发命中率偏低属预期。
