import { z } from 'zod';

/** 单个行业的宽度序列; series 与快照 dates 等长, 无数据位为 null. */
export const BreadthRowSchema = z.object({
  name: z.string(),
  series: z.array(z.number().nullable()),
  latest: z.number().nullable(),
});
export type BreadthRow = z.infer<typeof BreadthRowSchema>;

export const MarketPointSchema = z.object({
  date: z.string(),
  rate: z.number().nullable(),
});
export type MarketPoint = z.infer<typeof MarketPointSchema>;

/** 后端 market_temperature.json 契约 (对齐 market_breadth/pipeline.py). */
export const MarketTemperatureSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  source: z.string(),
  metric: z.string(),
  dates: z.array(z.string()),
  market: z.array(MarketPointSchema),
  industries_l1: z.array(BreadthRowSchema),
  industries_l2: z.array(BreadthRowSchema),
});
export type MarketTemperature = z.infer<typeof MarketTemperatureSchema>;

export type BreadthLevel = 'l1' | 'l2';
