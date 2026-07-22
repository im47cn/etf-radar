# ETF Radar — 跨市场主题联动分析平台

追踪 14 个美股主题 ETF 的强弱与动量, 自动映射到 A 股场内 ETF, 识别共振 / 传导 / 背离信号, 帮助 A 股个人投资者发现跨市场交易机会。

## 在线访问

- 主域: <https://im47.cn/etf-radar/> (自定义域名)
- 备用: <https://im47cn.github.io/etf-radar/> (GitHub Pages 默认)

## 页面 (v0.2+)

- `/` 跨市雷达 (默认) — 14 主题列表 + 信号详情 + A 股 ETF 映射
- `/rotation` 主题轮动 — 散点象限图, X=长期强度 Y=短期强度, 中线 50 切四象限, 气泡大小=综合排名

## 工作原理

1. GitHub Actions 按调度时间触发 Python 流水线 (`backend/src/pipeline.py`)
2. 从 **yfinance** (美股) 与 **AkShare** (A股) 拉取 ETF OHLC
3. 计算多周期对数收益率 → **双轨强度评分** (百分位 × sigmoid 动量) → 60 日相关性映射分 → 多周期投票信号
4. 输出到 `data/latest/{themes,etfs,signals,meta}.json` 并 commit 回仓库
5. 同时按日归档到 `data/snapshots/<YYYY-MM-DD>/`
6. 前端 (React + Vite + zod) 静态构建后部署到 GitHub Pages, 客户端 fetch JSON 渲染

## 调度计划 (北京时间)

| 时段 | Workflow | 内容 |
|------|----------|------|
| 工作日 06:30 | `us-refresh` | 美股全量刷新 |
| 工作日 09:15 | `cn-refresh` (full) | A 股全量刷新 + 重算信号 |
| 工作日 09:30-11:30 / 13:00-15:45 | `cn-refresh` (intraday) | 每 15 分钟刷新 A 股价格 |
| 工作日 15:30 | `cn-eod-archive` | 当日数据归档 |

## 本地开发

### Backend (Python 3.11+)

```bash
cd backend
uv venv && uv sync --extra dev
uv run pytest                              # 跑测试 (82 passed)
uv run python -m src.pipeline --mode=full --data-root=../data --config-dir=../config
```

### Frontend (Node 20+)

```bash
cd frontend
npm ci
npm run dev      # http://localhost:5173/etf-radar/
npm run build
npm test -- --run  # 27 tests
```

### 持仓监控本地开发（v3+）

`/portfolio` 路由需要 Supabase 凭据。**未配置不影响其他页面**，但 `/portfolio` 会显示"未配置"提示。

```bash
cp frontend/.env.local.example frontend/.env.local
# 编辑 .env.local，填入 Supabase Project URL 和 anon key
# 凭据可向项目维护者索取，或自行创建 Supabase 项目

npm run dev  # http://localhost:5173/etf-radar/#/portfolio
```

**Magic Link 登录**：邮件可能进国内邮箱（QQ/163）的垃圾箱，请检查；或使用 Google OAuth 一键登录。

**数据库 Schema**：见 `backend/migrations/001_user_holdings.sql`。在 Supabase SQL Editor 一次性执行。

### 首次种子数据 (需联网)

```bash
cd backend && uv run python ../scripts/bootstrap_data.py
git add data/latest/ && git commit -m "data: initial seed" && git push
```

### sigmoid K 参数校准 (可选, 需联网)

```bash
cd backend && uv run python ../scripts/calibrate_algo.py
```

输出不同 K 值下的强度分布, 偏差 ≤15% 标 ✓。根据结果调整 `config/algo.yml`。

### 数据归档与回填

每日 cron (`30 7 * * 1-5`, 即北京时间 15:30) 自动把 `data/latest/` 归档到 `data/snapshots/<BJT-date>/`，
供 Phase B 时间轴回放使用。`data/latest/snapshots-index.json` 由归档/回填脚本维护，前端 Phase B 据此发现可用日期。

**首次回填（一次性）**: 如果 snapshots 历史不足，运行回填脚本生成历史数据：

```bash
cd backend
uv run --all-extras python -m scripts.backfill_snapshots --start 2026-01-02 --end 2026-06-13
```

回填产物的 `meta.json` 含 `backfilled: true` 标记，区分自动归档。
`--skip-existing` 默认开启，保护已归档的真实数据。

### 归档清理 (>2 年自动删除, 通常不需要手动跑)

```bash
python scripts/archive_cleanup.py
```

### 历史快照回填 (Phase B 时间轴动画的数据基础)

`backend/scripts/backfill_snapshots.py` 可在不修改任何评分逻辑的前提下, 一次性重建过去 N 个交易日的 snapshots, 用于驱动 `/rotation` 时间轴动画。原理: `compute_outputs()` 接受 `asof_bjt` 锚点, 对内存中的 OHLC DataFrame 按日切片, 复用相同评分函数; meta.json 标记 `backfilled=true` 区分回填产物与实时归档。

```bash
cd backend && uv run --all-extras python -m scripts.backfill_snapshots \
  --start 2026-01-02 --end 2026-06-13 \
  --data-root ../data --config-dir ../config
```

- `--skip-existing` (默认开启) 保护既有归档, 不会覆盖真实 cron 产出
- `--force` 强制重写
- 输出: `data/snapshots/<YYYY-MM-DD>/{themes,signals,etfs,meta}.json` + `data/latest/snapshots-index.json`
- 全量 ~120 个交易日耗时 1-2 分钟 (网络拉取一次 + 内存切片)
- akshare 偶发限流, 失败的 CN ETF 会被记入 `meta.providers.cn.failed_symbols` 且整体 status 降为 `degraded`, 不影响其他主题

## 数据源 & 容灾

- 美股: **yfinance** (Yahoo Finance, 延迟 ~15 分钟)
- A 股: **AkShare** (东方财富数据, 延迟 ~15 分钟)
- **L1 软容灾**: 失败保留上次成功快照, UI 顶部黄色横幅告警 "数据已过期 XX 分钟"
- **mypy strict + ruff + jsonschema**: 数据契约多层验证 (Pydantic 写入 + JSON Schema 校验 + 前端 zod runtime parse)

## 部署

- GitHub Pages Source = **GitHub Actions** (用 `actions/deploy-pages`, 不走 Jekyll/`gh-pages` 分支)
- `deploy-frontend.yml` 触发条件: push 到 main 时 `frontend/**` 或 `data/latest/**` 有变更
- 数据 refresh workflow (cn/us-refresh) 结尾显式 `gh workflow run deploy-frontend.yml` 触发部署
  - 原因: `GITHUB_TOKEN` 推送的 commit 不触发下游 workflow (anti-loop 安全策略)
- Custom domain (可选): 当前配置为 `im47.cn`, 在 Settings → Pages → Custom domain 修改

## 关键文档

- 设计文档: [`docs/superpowers/specs/2026-06-05-etf-radar-design.md`](docs/superpowers/specs/2026-06-05-etf-radar-design.md)
- 实施计划: [`docs/superpowers/plans/2026-06-05-etf-radar-implementation.md`](docs/superpowers/plans/2026-06-05-etf-radar-implementation.md)
- 原产品文档: [`docs/htsc-us-cn-linkage-product-doc.md`](docs/htsc-us-cn-linkage-product-doc.md)
- 原需求文档: [`docs/htsc-us-cn-linkage-requirements.md`](docs/htsc-us-cn-linkage-requirements.md)

## 技术栈

| 层 | 技术 |
|----|------|
| Backend | Python 3.11, uv, pandas, scipy, pydantic v2, yfinance, akshare, chinese_calendar, pandas_market_calendars |
| Frontend | React 19, Vite 8, TypeScript strict, Tailwind v4, shadcn/ui, SWR, zod, Recharts, lucide-react |
| DevOps | GitHub Actions (5 workflows), GitHub Pages |
| 测试 | pytest (82 + 4 skipped), vitest (27), ruff, mypy strict, jsonschema |

## License

MIT
# test
