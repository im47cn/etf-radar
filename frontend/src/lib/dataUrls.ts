// 集中所有数据文件 URL 构造, 防止 URL 前缀错配 (publicDir 平铺结构) 再次潜伏.
// 背景: vite.config.ts `publicDir: '../data'` 把 ../data 的 *内容* (latest/, snapshots/)
// 平铺到 dist 根, 而非 dist/data/. 所有 fetch 必须用相对 BASE_URL 直接拼 latest/ 或
// snapshots/, 不能加 data/ 前缀. 该模块是唯一 URL 构造点, 配合契约测试杜绝错配.

const BASE = import.meta.env.BASE_URL ?? '/';

export const LATEST_URLS = {
  themes: `${BASE}latest/themes.json`,
  etfs: `${BASE}latest/etfs.json`,
  signals: `${BASE}latest/signals.json`,
  meta: `${BASE}latest/meta.json`,
  snapshotsIndex: `${BASE}latest/snapshots-index.json`,
  stocksSpot: `${BASE}latest/stocks_spot.json`,
  marketTemperature: `${BASE}latest/market_temperature.json`,
} as const;

// themes_path 形如 "snapshots/<date>/themes.json" (已含 snapshots/ 前缀, 由 backend 写入)
export const frameUrl = (themesPath: string): string => `${BASE}${themesPath}`;

// holdings 季度数据（独立于 snapshots）
export const HOLDINGS_URLS = {
  index: `${BASE}holdings/index.json`,
} as const;

export const holdingsEtfUrl = (etfCode: string): string =>
  `${BASE}holdings/${etfCode}.json`;

// Phase 2 个股指标
export const STOCKS_URLS = {
  holdingsIndicators: `${BASE}stocks/holdings_indicators.json`,
  index: `${BASE}stocks/index.json`,
} as const;

export const stockOhlcUrl = (stockCode: string): string =>
  `${BASE}stocks/ohlc/${stockCode}.json`;
