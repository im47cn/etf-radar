import { z } from 'zod';

// 与 backend tests/schemas/metals.schema.json 对齐; 全字段 nullish → null,
// 兼容组件降级(missing)时的历史/缺省产物 (schema 演进约定).
const num = z.number().nullish().transform((v) => v ?? null);
const str = z.string().nullish().transform((v) => v ?? null);

/** (date, value) 趋势点, 金银比 1 年日频. */
export const SeriesPointSchema = z.tuple([z.string(), z.number()]);
export type SeriesPoint = z.infer<typeof SeriesPointSchema>;

export const GoldSilverRatioSchema = z.object({
  value: num,
  percentile_5y: num,
  series: z.array(SeriesPointSchema).default([]),
});

/** 实际利率方向代理: TIP (iShares TIPS) 价格, 与实际利率反向. */
export const RealRateSchema = z.object({
  tip_price: num,
  change_60d: num,
  corr_gold_20d: num,
});

export const DxySchema = z.object({
  value: num,
  r_20d: num,
  r_60d: num,
});

/** 金矿杠杆比 GDX/GLD: 矿股相对金属的杠杆/情绪放大器. */
export const MinerLeverageSchema = z.object({
  ratio: num,
  percentile_1y: num,
});

export const CnEtfSchema = z.object({
  code: z.string(),
  name: str,
  price: num,
  r_1d: num,
  r_20d: num,
  r_60d: num,
  amount_yi: num,
  premium_pct: num,
});

export const CnSideSchema = z.object({
  gold_etf: CnEtfSchema.nullish().transform((v) => v ?? null),
  silver_lof: CnEtfSchema.nullish().transform((v) => v ?? null),
});

export const SourceStatusSchema = z.record(z.string(), z.enum(['ok', 'missing']));

export const MetalsSchema = z
  .object({
    schema_version: z.string(),
    generated_at: z.string(),
    as_of: str,
    gold_silver_ratio: GoldSilverRatioSchema,
    real_rate: RealRateSchema,
    dxy: DxySchema,
    miner_leverage: MinerLeverageSchema,
    cn_side: CnSideSchema,
    source_status: SourceStatusSchema,
  })
  .passthrough();
export type Metals = z.infer<typeof MetalsSchema>;
