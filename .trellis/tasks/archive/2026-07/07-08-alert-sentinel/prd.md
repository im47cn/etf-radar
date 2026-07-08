# C1 · 告警渠道 + 哨兵自愈骨架

> parent: `07-08-data-fetch-resilience`（D1 全自动自愈 / D2 哨兵架构 / D3 Server酱告警）

## Goal
建立自愈 hub:一个独立 health-monitor workflow 定时巡检数据新鲜度与各关键 workflow 运行状态,发现异常→自动触发补偿→计数上限内自愈,耗尽后经 Server酱 推微信告警。天然覆盖"cron 漏触发"(今天 09:15 cn-refresh 没跑无人知)。

## 确认事实(代码勘察)
- 已有 Resend 发信(`notify/digest.py`,dataclass+env 模式);无失败告警设施。Server酱需新增。
- `meta.json` 前端类型齐全(`frontend/src/types/meta.ts`),含 `providers.{cn,us}.status`(ok/fallback/degraded/stale)、`stale_minutes`、`cn_data_date`、`calendar`。哨兵可直接读同一 meta 判定新鲜度。
- `market_breadth_qc.json` 有 `over_threshold`(reconcile 产出),可作温度链陈旧信号。
- 关键 workflow:cn-refresh、us-refresh、stocks-daily、cn-eod-archive、membership-digest。可用 `gh run list --workflow=<f> --json` 查最近 run 状态/时间。
- C4 将产出 `stocks_continuity.missing_trading_days` + CLI(exit 3=缺口),哨兵复用。

## Requirements
- R1.1 **Server酱 渠道**:新增 `backend/src/notify/alert.py`,`send_alert(title, desp)` POST `https://sctapi.ftqq.com/<SENDKEY>.send`;env `SERVERCHAN_SENDKEY`;dry-run 支持;失败不抛致命(告警失败不该拖垮巡检)。
- R1.2 **哨兵巡检逻辑**:`backend/src/health_monitor.py`,读 `data/latest/meta.json` + `market_breadth_qc.json` + close_series 连续性,判定:provider degraded/stale、stale_minutes 超阈、对账 over_threshold、close_series 缺口。产出结构化 findings。
- R1.3 **run 状态巡检**:检查关键 workflow 最近 run 是否 期望时间内成功(覆盖"漏触发"与"失败")。
- R1.4 **补偿编排 + 计数**:每类异常映射补偿动作(`gh workflow run <对应>`);同一异常带重试计数上限(避免风暴),状态用轻量持久化(见 design)。
- R1.5 **兜底告警**:补偿耗尽或不可自愈 → `send_alert`。
- R1.6 **health-monitor.yml**:cron 每小时(交易时段可加密),`workflow_dispatch`;调用 health_monitor;需 `SERVERCHAN_SENDKEY` + `DATA_BOT_PAT`(触发别的 workflow)。

## Acceptance Criteria
- [ ] 单测:`send_alert` dry-run 不发网络;真实 path monkeypatch requests 断言 payload。
- [ ] 单测:health_monitor 判定——构造 stale/degraded/over_threshold/gap 的 meta → 命中对应 finding;健康 meta → 无 finding。
- [ ] 单测:计数上限——同一异常连续 N 次后不再补偿、转告警。
- [ ] workflow YAML 语法自检通过。
- [ ] 回归 `uv run --all-extras pytest` 全绿。
- [ ] 手动:构造 degraded meta → 触发 health-monitor → 观察补偿 dispatch + (耗尽后)告警。

## Out of scope
- 各具体补偿动作内部逻辑(属 C4 等);C1 只负责"发现→触发→告警"。
- 前端展示(属 C2)。

## 依赖 / 交界
- 依赖 C4 的 `stocks_continuity`(缺口检测)。若 C4 未先落地,C1 可先用 meta/qc 判定,close_series 缺口检测留 TODO 待 C4 合入。
- 补偿目标 workflow 的并发组由各自保证(backfill 已有)。
