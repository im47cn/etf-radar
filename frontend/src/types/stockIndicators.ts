/**
 * 后端数据契约（与 backend Pydantic models 对齐）：
 *   StockIndicators ↔ data/stocks/holdings_indicators.json::stocks[code]
 *   StockOhlcBar / StockOhlc ↔ data/stocks/ohlc/{code}.json
 */

import { z } from 'zod';

// 历史 snapshot 缺省字段兼容: .nullish().transform(v => v ?? null) (CLAUDE.md 规定模式)
const nullableNum = () => z.number().nullish().transform(v => v ?? null);

export const StockIndicatorsSchema = z.object({
  name:           z.string(),
  strength_60d:   nullableNum(),
  strength_20d:   nullableNum(),
  rsi_14:         nullableNum(),
  vol_ratio:      nullableNum(),
  leader:         z.enum(['⭐⭐⭐', '⭐⭐', '⭐', '']),
  vol_forecast_ann: nullableNum(), // GARCH 前瞻波动, 旧数据/拟合失败缺省
});

export const HoldingsIndicatorsFileSchema = z.object({
  schema_version: z.string(),
  generated_at:   z.string(),
  stocks:         z.record(z.string(), StockIndicatorsSchema),
});

export const StockOhlcSchema = z.object({
  code:         z.string(),
  name:         z.string(),
  generated_at: z.string(),
  bars:         z.array(z.object({
    date: z.string(),
    o: z.number(), h: z.number(), l: z.number(), c: z.number(), v: z.number(),
  })),
});

export type LeaderStar = '⭐⭐⭐' | '⭐⭐' | '⭐' | '';

export interface StockIndicators {
  name: string;
  strength_60d: number | null;
  strength_20d: number | null;
  rsi_14: number | null;
  vol_ratio: number | null;
  leader: LeaderStar;
  /** GARCH(1,1) 前瞻 60 日年化波动 (会员风控维度); 旧数据/拟合失败缺省 */
  vol_forecast_ann?: number | null;
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
