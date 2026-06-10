# ETF Radar

跨市场主题联动分析平台 — 追踪美股主题 ETF 强弱并映射到 A 股 ETF, 识别共振 / 传导 / 背离信号。

> 设计文档: [docs/superpowers/specs/2026-06-05-etf-radar-design.md](docs/superpowers/specs/2026-06-05-etf-radar-design.md)
> 实施计划: [docs/superpowers/plans/2026-06-05-etf-radar-implementation.md](docs/superpowers/plans/2026-06-05-etf-radar-implementation.md)

## 部署

首次部署后需在 GitHub Settings → Pages 设置 Source = `gh-pages` branch / `(root)`。
访问 URL 形如 `https://<owner>.github.io/etf-radar/`。

## GitHub Actions 调度 (UTC → BJT)

| Workflow | Cron (UTC) | BJT 含义 |
|---|---|---|
| `us-refresh` | `30 22 * * 1-5` | 工作日 06:30 美股全量 |
| `cn-refresh` (full) | `15 1 * * 1-5` | 工作日 09:15 A 股盘前 |
| `cn-refresh` (intraday 上午) | `30,45 1 * * 1-5` + `*/15 2-3 * * 1-5` | 09:30-11:45 每 15 分钟 |
| `cn-refresh` (intraday 下午) | `*/15 5-7 * * 1-5` | 13:00-15:45 每 15 分钟 |
| `cn-eod-archive` | `30 7 * * 1-5` | 15:30 EOD 归档 |
| `deploy-frontend` | push to `main` (paths: frontend/**, data/latest/**) | 自动部署 |
| `ci` | PR + push to main | pytest + ruff + mypy + npm build |

完整说明将在 Phase 9 补充。
