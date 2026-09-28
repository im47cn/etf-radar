/**
 * 后端数据契约（与 backend Pydantic models 对齐）：
 *   EtfTopHolding ↔ data/holdings/{code}.json::top_holdings[*]
 *   EtfHoldingsSnapshot ↔ data/holdings/{code}.json
 *   StockSpot ↔ data/latest/stocks_spot.json::stocks[code]
 *
 * 注意：本文件类型名与 @/lib/portfolio/types 的 Holding（用户持仓）刻意不重名。
 */

import { z } from 'zod';
import type { StockIndicators } from './stockIndicators';

// runtime 校验 schema (CLAUDE.md: 前端 zod 校验所有 JSON; 缺省字段走 nullish 兼容)
export const EtfTopHoldingSchema = z.object({
  code:   z.string(),
  name:   z.string(),
  weight: z.number(),
});

export const EtfHoldingsSnapshotSchema = z.object({
  etf_code:        z.string(),
  etf_name:        z.string(),
  disclosure_date: z.string(),
  fetched_at:      z.string(),
  top_holdings:    z.array(EtfTopHoldingSchema),
});

export const StockSpotSchema = z.object({
  name:  z.string(),
  close: z.number(),
  r_1d:  z.number().nullish().transform(v => v ?? null),
});

export const StocksSpotFileSchema = z.object({
  schema_version: z.string(),
  generated_at:   z.string(),
  stocks:         z.record(z.string(), StockSpotSchema),
});

export interface EtfTopHolding {
  code: string;       // 6 位 A 股或 5 位港股
  name: string;
  weight: number;     // 占 ETF 净值百分比 0-100
}

export interface EtfHoldingsSnapshot {
  etf_code: string;
  etf_name: string;
  disclosure_date: string;   // YYYY-MM-DD
  fetched_at: string;        // ISO 8601 带时区
  top_holdings: EtfTopHolding[];
}

export interface HoldingsIndexEntry {
  code: string;
  disclosure_date: string;
}

export interface HoldingsIndex {
  schema_version: string;
  generated_at: string;
  etfs: HoldingsIndexEntry[];
}

export interface StockSpot {
  name: string;
  close: number;
  r_1d: number | null;       // 小数形态（0.025 = +2.5%）
}

export interface StocksSpotFile {
  schema_version: string;
  generated_at: string;
  stocks: Record<string, StockSpot>;
}

export interface AggregatedStock {
  code: string;
  name: string;
  cumulativeWeight: number;   // 同股出现在多 ETF 时累加
  sourceEtfs: string[];       // 出现在哪些 ETF 代码中（去重）
  spot: StockSpot | null;     // null 表示停牌或 spot 缺失
  indicators?: StockIndicators;  // Phase 2 新增，可选；缺失时表格显示 "—"
}
