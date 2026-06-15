# ETF Radar — 跨市场主题联动分析平台

追踪 14 个美股主题 ETF 的强弱与动量, 自动映射到 A 股场内 ETF, 识别共振 / 传导 / 背离信号, 帮助 A 股个人投资者发现跨市场交易机会。

## 在线访问

- 主域: <https://im47.cn/etf-radar/> (自定义域名)
- 备用: <https://im47cn.github.io/etf-radar/> (GitHub Pages 默认)

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

### 归档清理 (>2 年自动删除, 通常不需要手动跑)

```bash
python scripts/archive_cleanup.py
```

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
