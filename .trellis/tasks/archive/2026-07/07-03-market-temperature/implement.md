# 执行计划 — 市场温度页面

按顺序执行；每个里程碑末尾为验证/评审门。后端优先跑通数据，再做前端。

## M0 — 准备与勘查
- [ ] 读 `src/output/snapshots_index.py`：确认索引是「目录扫描」还是「固定文件名清单」，决定 M1.5 是否需改。
- [ ] 读 `src/output/archiver.py`：确认归档是整目录复制（预期无需改）。
- [ ] 确认 `cn-refresh.yml` 实际调用的 backend 入口命令，定位追加步骤的位置。
- [ ] 确认 backend 已有 `httpx` 依赖（`pyproject.toml`）；若无则加入。

## M1 — 后端数据管线（TDD）
- [ ] `src/market_breadth/industry_mapping.py`：移植 skill 的 86→26 映射，导出 `L2_TO_L1`、`L1_ORDER`。加断言测试：所有一级都有子行业、无重复键。
- [ ] `src/providers/dapanyuntu_provider.py`：`fetch_breadth()`，headers + 超时 + 异常映射（403/超时/空→ProviderError/EmptyDataError）。测试用 mock httpx 响应（成功 / 403 / 空 data）。
- [ ] `src/market_temperature_pipeline.py`：`compute_market_temperature(raw)`：
  - 稀疏三元组解包 + 0 值过滤
  - `industries_l2` / `industries_l1`（等权聚合）/ `market`（全市场均值）
  - 缺失日 `null` 填充、行业按 latest 降序
  - 测试：小型构造数据覆盖 0 过滤、缺失 null、L1 聚合值、全市场均值、排序。
- [ ] `run(data_root)`：串 fetch→compute→`atomic_write_json`。
- **验证**：`cd backend && uv run --all-extras pytest tests/ -k "temperature or breadth or dapanyuntu" -v 2>&1 | tail -20`
- **门**：真实拉一次线上数据跑 `run`，人工核对全市场当日数字与 dapanyuntu 页面一致（±0.1）。

## M1.5 — 归档 / 索引接入
- [ ] 若 snapshots_index 为固定清单：补 `market_temperature_path`；否则跳过。
- [ ] 手动 archive 一次，确认 `data/snapshots/<date>/market_temperature.json` 生成、index 含条目。
- **验证**：`cd backend && uv run --all-extras pytest tests/test_snapshots_index.py -v 2>&1 | tail -20`

## M2 — 编排接入 cn-refresh
- [ ] 在 ETF pipeline 步骤后追加 `python -m src.market_temperature_pipeline`。
- [ ] 失败隔离：`continue-on-error` 或入口 try/except，拉取失败不阻断主流程、保留旧快照并记日志。
- **门**：本地模拟 refresh 流程跑通；断网/403 时主流程不崩。

## M3 — 前端数据层
- [ ] `types/marketTemperature.ts`：zod schema + 类型。
- [ ] `hooks/useMarketTemperature.ts`：SWR 拉 `/data/latest/market_temperature.json`，缺失优雅降级。
- **验证**：`cd frontend && npx vitest run src/hooks/__tests__/useMarketTemperature.test.tsx 2>&1 | tail -30`

## M4 — 前端页面与组件
- [ ] `components/temperature/MarketThermometer.tsx`（大数字 + 配色 + sparkline）
- [ ] `components/temperature/IndustryRanking.tsx`（条形排行 + l1/l2）
- [ ] `components/temperature/BreadthHeatmap.tsx`（行业×日期矩阵，浅色系色阶）
- [ ] `components/temperature/TemperaturePage.tsx`（容器 + `level` 状态 + 口径说明文案）
- [ ] `App.tsx` 加 `/temperature` 路由；Header 加导航入口。
- **验证**：`cd frontend && npx vitest run src/components/temperature 2>&1 | grep -E "Test Files|Tests|✓|×" | tail -30`

## M5 — 集成验证与回归
- [ ] 前端起本地，用真实快照肉眼验收三块 + l1/l2 联动 + 口径文案 + 31 列对齐。
- [ ] 后端全量回归：`cd backend && uv run --all-extras pytest 2>&1 | tail -15`
- [ ] 前端全量回归：`cd frontend && npx vitest run 2>&1 | grep -E "^(Test Files|Tests)" | tail`
- [ ] 逐条核对 prd.md 验收标准。

## 回滚点
- M1/M2 后端可独立回滚（删新增文件 + 撤 cn-refresh 步骤）。
- M4 前端可独立回滚（撤路由 + 导航条目）。
- 历史快照中的 `market_temperature.json` 残留无害，无需清理。

## 评审门
- M1 完成 → dispatch `trellis-check` 审后端数据正确性。
- M4 完成 → dispatch `trellis-check` 审前端。
- M5 → 最终集成审 + prd 验收核对。
