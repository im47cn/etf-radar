import { z } from 'zod';

/** 单只指数收盘价序列; series 与顶层 dates 等长, 缺失日为 null. */
export const IndexSeriesEntrySchema = z.object({
  code: z.string(),
  name: z.string(),
  // .nullish().transform 兼容历史 snapshot 缺省字段 (项目规则)
  series: z.array(z.number().nullish().transform((v) => v ?? null)),
});
export type IndexSeriesEntry = z.infer<typeof IndexSeriesEntrySchema>;

/** data/latest/index_series.json 契约 (schema 1.0). dates 与 market_temperature.json 完全一致. */
export const IndexSeriesSchema = z
  .object({
    schema_version: z.string(),
    generated_at: z.string().optional(),
    dates: z.array(z.string()),
    indices: z.array(IndexSeriesEntrySchema),
  })
  .passthrough();
export type IndexSeries = z.infer<typeof IndexSeriesSchema>;
