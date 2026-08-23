# ETF Radar — Cross-Market Theme Linkage Analysis

Tracks US theme ETF strength and momentum, auto-maps them to China A-share ETFs, and identifies resonance /传导 / divergence signals. Also provides a market temperature gauge (MA20/MA5 standing rate), constituent stock analysis, and portfolio monitoring to help A-share retail investors spot cross-market opportunities.

[**中文文档**](README.zh-CN.md)

## Live Demo

- Primary: <https://im47.cn/etf-radar/> (custom domain)
- Fallback: <https://im47cn.github.io/etf-radar/> (GitHub Pages default)

## Pages

| Route | Name | Description |
|-------|------|-------------|
| `/` `/temperature` | Temperature | Market temperature gauge — MA20/MA5 standing rate, 2nd/1st-level industry aggregation + heatmap (default landing page) |
| `/rotation` | Rotation | Theme rotation scatter quadrant — X=long-term strength, Y=short-term strength, midline 50 splits four quadrants |
| `/radar` | Radar | Cross-market radar — theme list + signal details + A-share ETF mapping |
| `/evidence` | Evidence | Signal evidence — IC rolling/horizon charts + ARCH diagnostics + scorecard (requires membership) |
| `/grid` | Grid | Grid trading & suitability analysis (requires membership) |
| `/metals` | Metals | Precious-metals macro indicator — gold/silver ratio percentile (descriptive, no alpha claimed) |
| `/trading` | Trading | Environment / signals / positions / review tabs (env tab free; other tabs require membership) |
| `/theme/:id/stocks` | Stocks | Theme constituent stock analysis (A-share ETF holdings + spot + technical indicators) |
| `/portfolio` → `/trading?tab=holdings` | 持仓（重定向） | Legacy portfolio entry — redirects to Trading 主题持仓 tab |
| `/watchlist` | Watchlist | Personal watchlist (requires login + membership; entry lives in Trading 自选 tab) |
| `/membership` | Membership | Membership info |
| `/auth/callback` | — | Magic Link / OAuth login callback |

## How It Works

1. GitHub Actions triggers the Python pipeline on a schedule (`backend/src/pipeline.py`)
2. Fetches ETF OHLC data from **yfinance** (US) and **AkShare** (China A-shares)
3. Computes multi-period log returns → **dual-track strength scoring** (percentile × sigmoid momentum) → 60-day correlation mapping score → multi-period voting signals
4. Writes to `data/latest/{themes,etfs,signals,meta}.json` and commits back to the repo
5. Archives daily to `data/snapshots/<YYYY-MM-DD>/`
6. Frontend (React + Vite + zod) builds statically and deploys to GitHub Pages; client fetches JSON for rendering

## Schedule (Beijing Time, UTC+8)

| Time | Workflow | Description |
|------|----------|-------------|
| Weekdays 06:30 | `us-refresh` | US market full refresh |
| 1st of month 08:30 | `holdings-refresh` | Monthly holdings refresh |
| Weekdays 09:15 | `cn-refresh` (full) | A-share full refresh + signal recompute + market temperature |
| Weekdays 09:30-11:45 / 13:00-15:45 | `cn-refresh` (intraday) | A-share price refresh every 15 min |
| Weekdays 09:00-15:30 | `stocks-spot-refresh` | Stock spot snapshot every 30 min |
| Weekdays 16:30 | `stocks-daily` | Stock daily candle increment + self-heal check |
| Weekdays 17:00 | `trading-eod` | Trading signal EOD — OHLCV increment + signal pipeline + review & notify (staggered 30 min after stocks-daily) |
| Weekdays 18:00 | `cn-eod-archive` | Post-close EOD full refresh + daily archive |
| Hourly :05 | `health-monitor` | Data freshness check + critical workflow self-heal |
| 2nd of month 04:00 | `stock-industry-map` | Stock → JR (juchao) industry mapping refresh |
| 2nd of month 08:07 | `evidence-monthly` | Signal evidence computation (IC + ARCH) + commit & deploy |
| Manual | `membership-digest` | Membership change digest email |
| Manual | `stocks-history-backfill` | Stock history backfill |
| Manual | `stocks-archive` | Monthly/yearly archive sharding (overseas IP rate-limited; dispatch manually) |

## Local Development

### Backend (Python 3.11+)

```bash
cd backend
uv venv && uv sync --extra dev
uv run pytest                              # run tests (see CI for counts)
uv run python -m src.pipeline --mode=full --data-root=../data --config-dir=../config
```

### Frontend (Node 20+)

```bash
cd frontend
npm ci
npm run dev      # http://localhost:5173/etf-radar/
npm run build
npm test -- --run  # run tests (see CI for counts)
```

### Portfolio / Watchlist Local Dev

The `/portfolio` and `/watchlist` routes require Supabase credentials. **Other pages work fine without them**, but these pages will show an "unconfigured" notice.

```bash
cp frontend/.env.local.example frontend/.env.local
# Edit .env.local with your Supabase Project URL and anon key
# Ask the project maintainer for credentials, or create your own Supabase project

npm run dev  # http://localhost:5173/etf-radar/#/trading?tab=holdings
```

**Magic Link login**: emails may land in the spam folder of Chinese mailboxes (QQ/163) — please check; or use Google OAuth for one-click login.

**Database Schema**: see `backend/migrations/001_user_holdings.sql` and subsequent migration files; execute them sequentially in the Supabase SQL Editor.

### Initial Data Seed (requires network)

```bash
cd backend && uv run python ../scripts/bootstrap_data.py
git add data/latest/ && git commit -m "data: initial seed" && git push
```

### Sigmoid K Parameter Calibration (optional, requires network)

```bash
cd backend && uv run python ../scripts/calibrate_algo.py
```

Outputs strength distributions at different K values; deviation ≤15% is marked ✓. Adjust `config/algo.yml` accordingly.

### Data Archiving & Backfill

A daily cron archives `data/latest/` to `data/snapshots/<BJT-date>/`. The `data/latest/snapshots-index.json` is maintained by the archive/backfill scripts; the frontend uses it to discover available dates.

**First-time backfill (one-off)**: if snapshot history is insufficient, run the backfill script to generate historical data:

```bash
cd backend
uv run --all-extras python -m scripts.backfill_snapshots --start 2026-01-02 --end 2026-06-13
```

Backfilled `meta.json` carries a `backfilled: true` flag to distinguish from automated archives. `--skip-existing` is on by default to protect real archived data.

### Historical Snapshot Backfill (data basis for timeline animation)

`backend/scripts/backfill_snapshots.py` can rebuild snapshots for the past N trading days in one pass without modifying any scoring logic, used to drive the `/rotation` timeline animation. How it works: `compute_outputs()` accepts an `asof_bjt` anchor, slices the in-memory OHLC DataFrame by day, and reuses the same scoring functions.

```bash
cd backend && uv run --all-extras python -m scripts.backfill_snapshots \
  --start 2026-01-02 --end 2026-06-13 \
  --data-root ../data --config-dir ../config
```

- `--skip-existing` (on by default) protects existing archives; will not overwrite real cron output
- `--force` forces rewrite
- Output: `data/snapshots/<YYYY-MM-DD>/{themes,signals,etfs,meta}.json` + `data/latest/snapshots-index.json`
- ~120 trading days take 1-2 minutes (one network fetch + in-memory slicing)
- akshare occasional rate limiting: failed CN ETFs are recorded in `meta.providers.cn.failed_symbols` and overall status degrades to `degraded`; other themes are unaffected

### Archive Cleanup (>2-year auto-deletion, usually no manual run needed)

```bash
python scripts/archive_cleanup.py
```

## Data Sources & Resilience

- US market: **yfinance** (Yahoo Finance, ~15 min delay)
- A-shares: **AkShare** (Eastmoney data, ~15 min delay)
- Market temperature: **dapanyuntu.com** (market cloud map, 2nd-level industry MA20 standing rate)
- **L1 soft resilience**: on failure, retains the last successful snapshot; UI shows a yellow banner warning "data is XX minutes stale"
- **mypy strict + ruff + jsonschema**: multi-layer data contract validation (Pydantic on write + JSON Schema validation + frontend zod runtime parse)
- **Health monitor + self-heal**: hourly checks of data freshness and critical workflow run status; auto-dispatches compensating workflows on anomalies

## Deployment

- GitHub Pages Source = **GitHub Actions** (uses `actions/deploy-pages`; not Jekyll / `gh-pages` branch)
- `deploy-frontend.yml` trigger: push to main with changes in `frontend/**` or `data/latest/**`
- Data refresh workflows (cn/us-refresh) explicitly call `gh workflow run deploy-frontend.yml` at the end to trigger deployment
  - Reason: commits pushed by `GITHUB_TOKEN` do not trigger downstream workflows (anti-loop safety policy)
- Custom domain (optional): currently set to `im47.cn`; change in Settings → Pages → Custom domain

## Key Documents

- Design & implementation process docs: session-scoped artifacts, not tracked in-repo (see [docs/CONVENTIONS.md](docs/CONVENTIONS.md))
- Original product doc: [`docs/htsc-us-cn-linkage-product-doc.md`](docs/htsc-us-cn-linkage-product-doc.md)
- Original requirements: [`docs/htsc-us-cn-linkage-requirements.md`](docs/htsc-us-cn-linkage-requirements.md)

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, uv, pandas, numpy, scipy, pydantic v2, yfinance, akshare, chinese_calendar, pandas_market_calendars, ta (technical indicators) |
| Frontend | React 19, Vite, TypeScript strict, Tailwind v4, Base UI, Recharts, SWR, zod, react-router-dom, lucide-react |
| DevOps | GitHub Actions, GitHub Pages |
| Testing | pytest, vitest, ruff, mypy strict, jsonschema |

## License

MIT
