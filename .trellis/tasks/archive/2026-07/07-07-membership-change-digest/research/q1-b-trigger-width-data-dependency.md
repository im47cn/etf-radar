# Research: Q1 — B 触发「自选项宽度跨档」数据依赖是否成立

- **Query**: prd 的 B 触发要对自选 theme/ETF 判断宽度跨档；themes.json 只有 strength 无宽度，宽度在 market_temperature.json（行业/大类级）。B 能否 per-自选项落地？
- **Scope**: internal
- **Date**: 2026-07-07

## 结论（一句话）

**B 无法 per-自选项落地，建议本期剔除**（或降级为「行业级宽度提示」但价值低且有额外数据缺口）。A/C/D 已足够支撑 MVP 价值。

## 证据

### 1. market_temperature.json 结构（`data/latest/market_temperature.json`）

```
schema_version: '2.0'
metric: 'maN_above_ratio'          # 站上 MA 的个股占比
source: 'self'                     # 自建个股宽度
dates: [150 个交易日]
periods:
  ma20 / ma60 / ma120:            # 三个周期各一份
    market:        [150] 每项 {date, rate}          ← 全市场维度
    industries_l1: [11]  每项 {name, latest, series[150]}   ← 巨潮「门类」大类
    industries_l2: [86]  每项 {name, latest, l1, series[150]} ← 巨潮「大类」中类
```

- 维度只有三层：**全市场 / 巨潮门类(l1, 11 个) / 巨潮中类(l2, 86 个)**。**没有 theme 维度，也没有 ETF 维度。**
- l1 门类实测：`医药卫生 / 金融 / 主要消费 / 可选消费 / 原材料 / 工业 / 信息技术 / 房地产 / 公用事业 / 能源 / 电信业务`。
- l2 中类示例：`证券 / 化学制剂 / 化学原料药 …`（带 `l1` 父级）。
- 宽度来源：`backend/src/market_breadth/self_breadth.py`（个股 close_series + 巨潮行业映射直接聚合，见文件头 docstring 与 L52-120）。

### 2. theme→行业 映射：不存在（不可得）

- `ThemeConfig` 模型（`backend/src/models.py:19`）字段：`id, name, us_etfs, primary_us, primary_cn, tags, note, cn_etfs`。**无 industry / l1 / 门类字段。**
- 产出的 `themes.json` theme 对象字段：`id, name, us_etfs, primary_us, primary_cn, tags, note, returns, strength, us_strength, cn_strength, rank`。**同样无行业维度。**
- 唯一潜在桥梁是 `tags`（自由文本，如 半导体/券商/算力/新能源车…），但与巨潮门类命名体系不对齐：
  - `tags ∩ l1门类` 仅 5/11：`主要消费, 公用事业, 可选消费, 能源, 金融`
  - `tags ∩ l2中类` 仅 6/86：`传媒, 保险, 半导体, 煤炭, 生物科技, 银行`
  - 多数主题的核心 tag（半导体设备/算力/机器人/新能源车/储能/稀土…）无任何门类/中类对应。
- `grep -rniE "theme.*(industry|门类|行业|l1)|theme_to_ind|shenwan…" backend/src` → **无任何映射代码**。

结论：theme 与 market_temperature 是两套独立分类体系，无确定、稳定的映射。即便用 tag 模糊匹配，覆盖率低且需引入人工映射表（新魔数/新维护面），违背「不引新魔数、消除风险」的目标。

### 3. 附加数据缺口：market_temperature.json 并非每日产出

抽查近 30 个 snapshot 目录（2026-05-26 .. 2026-07-07）：

- `themes.json` 缺失：**无**（30/30 齐全）
- `etfs.json` 缺失：**无**（30/30 齐全）
- `market_temperature.json` 缺失：**27 天**（该功能约 2026-07-03 才上线，之前全缺；07-02 也缺）。

即：即便做行业级宽度，昨日 mt 文件很可能不存在 → B/C 都需对 mt 缺失做降级。

## 对 design / implement 的影响

1. **prd §15 触发事件 B / design §2.2 B / implement 阶段 1**：B「per 自选项宽度跨档」**不可实现**。建议：
   - **首选：本期剔除 B**，触发集合缩为 **A + C + D**。prd Acceptance Criteria 里「A/B/C/D 任一变化」改为「A/C/D」。
   - 备选（不推荐）：B 降级为「自选 theme 若能通过 tag 命中某门类/中类，则提示该行业宽度跨档」——覆盖率低、需人工映射表、引入新维护面，投入产出比差。
2. **design §7 开放问题 1** 可据此关闭：结论=剔除。
3. **C 触发同样受 mt 缺失影响**（见 Q3 文件）：需对「昨日/今日 mt 文件不存在」安全降级（跳过 C，不报错）——与 prd Acceptance Criteria「数据缺失安全降级」一致。

## Caveats / Not Found

- 未排查是否可在 `self_breadth.py` 里新增 theme 级宽度产出（个股→theme 成分聚合）——那是新增数据管线工作，超出「复用现有分档、消除风险」范围，不建议塞进本任务。
- tag 模糊匹配的确切覆盖率基于 `config/themes.yml` 当前 30 主题，未来主题增改会漂移。
