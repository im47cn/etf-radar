# 执行计划 — 个股宽度多周期自建管线

顺序推进；M0 是**决定性 spike 门**，未过不进后续。每里程碑末尾有验证/评审门。

## M0 — 股票→行业映射 spike ✅ 已完成
结论（详见 research/m0-industry-mapping-spike.md）：
- 东财 CI 实测 **0/5 全挂**（RemoteDisconnected）→ 证伪。
- 申万成分接口 akshare bug + SSL 被墙 → 不可用。
- **定源=巨潮 `stock_industry_change_cninfo`（逐股）**：层级(大类/中类)自带，映射与体系一次到手。
- dapanyuntu 对账降级为**仅全市场**。
- probe workflow 用完，收尾时删除 `.github/workflows/probe-industry-source.yml`。

## M1 — 历史深度加深到 150
- [ ] `stocks_history_pipeline.py` `--days` 默认 → 150；`stocks-history-backfill.yml` 默认值同步。
- [ ] `stocks_daily_pipeline.py` `WINDOW_DAYS` → 150。
- [ ] 手动触发 backfill days=150；校验 `close_series.json` dates 长度 ≥150。
- **验证**：`python3 -c "import json;print(len(json.load(open('data/stocks/close_series.json'))['dates']))"` ≥150
- **门**：确认次日 daily 增量不把深度截回 75（读代码确认 WINDOW_DAYS 生效路径）。

## M2 — 股票→行业映射管线（巨潮）
- [ ] `providers/stock_industry_provider.py`：`fetch_stock_industry(code)` 调 `ak.stock_industry_change_cninfo`，筛"最新巨潮标准"行取 {l1=行业大类, l2=行业中类}，异常包装。
- [ ] `market_breadth/stock_industry_pipeline.py`：复用 ThreadPoolExecutor 并发骨架遍历 close_series 5531 code，产出 `data/stocks/stock_industry_map.json`（map:{code:{l1,l2}} + unmapped）。
- [ ] 韧性：单股重试 + **持久缓存断点续跑**（合并上次 good map），覆盖率 ≥95% 否则告警但用旧 map。
- **验证**：`pytest -k stock_industry`（mock akshare，验证筛选规则/多标准取最新/断点合并）；小样本真实跑看覆盖率与样例。
- **门**：真实全量跑一次（月级 job），确认 5531 并发在本地/CI 的成功率与耗时可接受。

## M3 — 宽度计算（纯函数核心，TDD）
- [ ] `market_breadth/self_breadth.py`：`compute_self_breadth(close_series, industry_map, periods) -> snapshot(schema 2.0)`。
  - SMA_n（前缀和 O(n)）、站上判定、有效样本（非 null + 历史≥n）过滤
  - 全市场个股占比 / 二级 / 一级(成分合并) / 多周期
- [ ] 测试：小矩阵覆盖 SMA、新股(历史不足)排除、停牌(null)排除、全市场占比、一级成分合并、MA120 历史不足→null。
- [ ] `run(data_root)`：读 close_series+map → 计算 → 写 `market_temperature.json`(2.0)。
- **验证**：`pytest -k "self_breadth or breadth"`；真实跑一次，人工抽样核 1 个行业 1 天：站上数/有效数。
- **门**：`trellis-check` 审计算正确性。

## M4 — dapanyuntu 对账 QC
- [ ] dapanyuntu 输出改名 `market_breadth_qc_dapanyuntu.json`（不再主展示）。
- [ ] `market_breadth/reconcile.py`：自算 MA20 vs dapanyuntu 二级行业偏差 → `market_breadth_qc.json`；阈值据首跑定，超阈 warning。
- **验证**：真实对账一次，看偏差分布是否落合理区间（判断方法学差异是否可接受）。

## M5 — 编排接入
- [ ] `cn-refresh.yml`：dapanyuntu step 后追加 self_breadth + reconcile（continue-on-error）。
- [ ] 映射刷新独立低频 workflow。
- [ ] `archiver.py` FILES 追加 `market_breadth_qc.json`。
- **门**：本地模拟 refresh 跑通；任一步失败不阻断主链、保留旧快照。

## M6 — 前端多周期
- [ ] `types/marketTemperature.ts`：schema 2.0（periods），兼容 1.0。
- [ ] `hooks/useMarketTemperature.ts`：暴露 periods + 可用周期。
- [ ] `TemperaturePage.tsx`：全局 MA20/60/120 切换器（MA120 缺失禁用+提示），联动三块；口径文案改个股级。
- [ ] 三组件复用（签名基本不变）。
- **验证**：`vitest run src/components/temperature src/hooks`；起 dev server 截图验收三周期切换 + MA120 缺失态。
- **门**：`trellis-check` 审前端。

## M7 — 集成验证与回归
- [ ] 后端全量：`cd backend && uv run --all-extras pytest 2>&1 | tail -15`
- [ ] 前端全量：`cd frontend && npx vitest run`
- [ ] 逐条核对 prd 验收标准；肉眼验收多周期页面。

## 评审门汇总
- M0 spike 报告 → 用户/我复核，定映射源。
- M3 → trellis-check（计算正确性）。
- M6 → trellis-check（前端）。
- M7 → 最终集成 + prd 核对。

## 回滚点
- M1（历史深度）可独立回滚（--days 改回 75）。
- M2/M3/M4 后端可独立回滚（删新增文件 + 撤 cron step；页面临时切回 dapanyuntu 输出）。
- M6 前端可独立回滚（撤周期切换器，退回单 MA20 读取）。
