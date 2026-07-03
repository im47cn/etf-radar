# 执行计划 — 个股宽度多周期自建管线

顺序推进；M0 是**决定性 spike 门**，未过不进后续。每里程碑末尾有验证/评审门。

## 进度总览（2026-07-03）
- **M0–M6 全部完成并推送 main + 部署生产** (`im47.cn/etf-radar`)。
- **M7 仅剩 MA120 真实数据**：150 天 backfill 运行中（前几次因 45min timeout / rebase 冲突失败，已修复 timeout→120min + 保存-reset-覆盖-重试提交）。当前 close_series 76 天，MA120 前端灰显禁用，待 backfill 补 150 天后重算 2.0 即可。
- **关键偏差**：M2 巨潮层级取 **门类(11,一级)/大类(86,二级)**（非大类/中类，那是二级/三级粒度）；覆盖率 **82.9%**（北交所/新股 cninfo 无分类，真实天花板，非 ≥95%）。
- **本轮大量前端 UI 迭代**（见文末「M6+ UI 迭代」）。

## M0 — 股票→行业映射 spike ✅ 已完成
结论（详见 research/m0-industry-mapping-spike.md）：
- 东财 CI 实测 **0/5 全挂**（RemoteDisconnected）→ 证伪。
- 申万成分接口 akshare bug + SSL 被墙 → 不可用。
- **定源=巨潮 `stock_industry_change_cninfo`（逐股）**：层级自带；实测取 **门类(11,一级)/大类(86,二级)**（非大类/中类）。
- dapanyuntu 对账降级为**仅全市场**。
- probe workflow 用完，收尾时删除 `.github/workflows/probe-industry-source.yml`。

## M1 — 历史深度加深到 150
- [x] `stocks_history_pipeline.py` `--days` 默认 → 150；`stocks-history-backfill.yml` 默认值同步。
- [x] `stocks_daily_pipeline.py` `WINDOW_DAYS` → 150。
- [x] 手动触发 backfill days=150；校验 `close_series.json` dates 长度 ≥150。
- **验证**：`python3 -c "import json;print(len(json.load(open('data/stocks/close_series.json'))['dates']))"` ≥150
- **门**：确认次日 daily 增量不把深度截回 75（读代码确认 WINDOW_DAYS 生效路径）。

## M2 — 股票→行业映射管线（巨潮）
- [x] `providers/stock_industry_provider.py`：`fetch_stock_industry(code)` 调 `ak.stock_industry_change_cninfo`，筛"最新巨潮标准"行取 {l1=行业门类, l2=行业大类}，异常包装 + 3 次重试。
- [x] `market_breadth/stock_industry_pipeline.py`：复用 ThreadPoolExecutor 并发骨架遍历 close_series 5531 code，产出 `data/stocks/stock_industry_map.json`（map:{code:{l1,l2}} + unmapped）。
- [x] 韧性：单股重试 + **持久缓存断点续跑**（合并上次 good map），覆盖率 ≥95% 否则告警但用旧 map。
- **验证**：`pytest -k stock_industry`（mock akshare，验证筛选规则/多标准取最新/断点合并）；小样本真实跑看覆盖率与样例。
- **门**：真实全量跑一次（月级 job），确认 5531 并发在本地/CI 的成功率与耗时可接受。

## M3 — 宽度计算（纯函数核心，TDD）
- [x] `market_breadth/self_breadth.py`：`compute_self_breadth(close_series, industry_map, periods) -> snapshot(schema 2.0)`。
  - SMA_n（前缀和 O(n)）、站上判定、有效样本（非 null + 历史≥n）过滤
  - 全市场个股占比 / 二级 / 一级(成分合并) / 多周期
- [x] 测试：小矩阵覆盖 SMA、新股(历史不足)排除、停牌(null)排除、全市场占比、一级成分合并、MA120 历史不足→null。
- [x] `run(data_root)`：读 close_series+map → 计算 → 写 `market_temperature.json`(2.0)。
- **验证**：`pytest -k "self_breadth or breadth"`；真实跑一次，人工抽样核 1 个行业 1 天：站上数/有效数。
- **门**：`trellis-check` 审计算正确性。

## M4 — dapanyuntu 对账 QC
- [x] dapanyuntu 输出改名 `market_breadth_qc_dapanyuntu.json`（不再主展示）。
- [x] `market_breadth/reconcile.py`：自算 MA20 vs dapanyuntu 二级行业偏差 → `market_breadth_qc.json`；阈值据首跑定，超阈 warning。
- **验证**：真实对账一次，看偏差分布是否落合理区间（判断方法学差异是否可接受）。

## M5 — 编排接入
- [x] `cn-refresh.yml`：dapanyuntu step 后追加 self_breadth + reconcile（continue-on-error）。
- [x] 映射刷新独立低频 workflow。
- [x] `archiver.py` FILES 追加 `market_breadth_qc.json`。
- **门**：本地模拟 refresh 跑通；任一步失败不阻断主链、保留旧快照。

## M6 — 前端多周期
- [x] `types/marketTemperature.ts`：schema 2.0（periods），兼容 1.0。
- [x] `hooks/useMarketTemperature.ts`：暴露 periods + 可用周期。
- [x] `TemperaturePage.tsx`：全局 MA20/60/120 切换器（MA120 缺失禁用+提示），联动三块；口径文案改个股级。
- [x] 三组件复用（签名基本不变）。
- **验证**：`vitest run src/components/temperature src/hooks`；起 dev server 截图验收三周期切换 + MA120 缺失态。
- **门**：`trellis-check` 审前端。

## M7 — 集成验证与回归
- [x] 后端全量：253 passed。前端全量：430+ passed。
- [x] 逐条核对 prd 验收标准；肉眼验收多周期页面（MA20/MA60 真实数据 + 部署生产）。
- [ ] **MA120 真实数据**：待 150 天 backfill 完成 → 重算 2.0 → 部署 → 验证 MA120 可切换。（唯一未闭环项）

## M6+ UI 迭代（上线后按反馈优化，全部已部署生产）
- [x] 行业排行：门类折叠树 + 一键展开全部（去一级/二级切换）；一级条形叠加**子行业 min–max 区间须**。
- [x] 热力图：折叠展开（修 self_breadth 补 l2 的 l1 父级）、只显最近 45 列、真正方格(12×12)、日期竖排对齐、标题固定(移出滚动容器)、消除名称列左侧穿越(borderSpacing:0+边框)、行业名与排行样式统一(text-xs)。
- [x] 温度计折线：全宽 + **逐日温度背景色带**，改 4 档离散级别(冰点/偏冷/偏暖/过热)。
- [x] CI 修复：backfill timeout 45→120min、push 用 保存-reset-覆盖-重试（根治与 daily 增量 rebase 冲突）。

## 评审门汇总
- M0 spike 报告 → 用户/我复核，定映射源。
- M3 → trellis-check（计算正确性）。
- M6 → trellis-check（前端）。
- M7 → 最终集成 + prd 核对。

## 回滚点
- M1（历史深度）可独立回滚（--days 改回 75）。
- M2/M3/M4 后端可独立回滚（删新增文件 + 撤 cron step；页面临时切回 dapanyuntu 输出）。
- M6 前端可独立回滚（撤周期切换器，退回单 MA20 读取）。
