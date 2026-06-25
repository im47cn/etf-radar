/**
 * 后端数据契约（与 backend Pydantic models 对齐）：
 *   StockIndicators ↔ data/stocks/holdings_indicators.json::stocks[code]
 *   StockOhlcBar / StockOhlc ↔ data/stocks/ohlc/{code}.json
 */

export type LeaderStar = '⭐⭐⭐' | '⭐⭐' | '⭐' | '';

export interface StockIndicators {
  name: string;
  strength_60d: number | null;
  strength_20d: number | null;
  rsi_14: number | null;
  vol_ratio: number | null;
  leader: LeaderStar;
}

export interface HoldingsIndicatorsFile {
  schema_version: string;
  generated_at: string;
  stocks: Record<string, StockIndicators>;
}

export interface StockOhlcBar {
  date: string;       // YYYY-MM-DD
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface StockOhlc {
  code: string;
  name: string;
  generated_at: string;
  bars: StockOhlcBar[];
}
