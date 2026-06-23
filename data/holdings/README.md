# data/holdings/

ETF 季报披露持仓数据，由 `backend/src/holdings_pipeline.py` 生成。

## 文件
- `{etf_code}.json` — 单只 ETF 的 top-10 持仓（披露日 + 抓取时间 + 个股列表）
- `index.json` — 所有成功抓取的 ETF 索引

## 更新机制
- `.github/workflows/holdings-refresh.yml` 每月 1 日 00:30 UTC 触发
- 季报披露窗口（1-4 月、4-5 月、7-8 月、10-11 月）后第一次月初运行才会变化

## 数据契约
见 [`docs/superpowers/specs/2026-06-23-theme-stocks-phase-1-design.md`](../../docs/superpowers/specs/2026-06-23-theme-stocks-phase-1-design.md)。
