import { z } from 'zod';

/** 单个行业的宽度序列; series 与快照 dates 等长, 无数据位为 null. */
export const BreadthRowSchema = z.object({
  name: z.string(),
  l1: z.string().optional(), // 仅二级行业携带其一级父级
  series: z.array(z.number().nullable()),
  latest: z.number().nullable(),
});
export type BreadthRow = z.infer<typeof BreadthRowSchema>;

export const MarketPointSchema = z.object({
  date: z.string(),
  rate: z.number().nullable(),
});
export type MarketPoint = z.infer<typeof MarketPointSchema>;

/** 单周期的三块数据. */
export const PeriodDataSchema = z.object({
  market: z.array(MarketPointSchema),
  industries_l1: z.array(BreadthRowSchema),
  industries_l2: z.array(BreadthRowSchema),
});
export type PeriodData = z.infer<typeof PeriodDataSchema>;

export type PeriodKey = 'ma20' | 'ma60' | 'ma120';
export const PERIOD_KEYS: PeriodKey[] = ['ma20', 'ma60', 'ma120'];
export const PERIOD_LABELS: Record<PeriodKey, string> = { ma20: 'MA20', ma60: 'MA60', ma120: 'MA120' };

// schema 2.0: 自建多周期
const V2Schema = z.object({
  schema_version: z.string(),
  dates: z.array(z.string()),
  periods: z.object({
    ma20: PeriodDataSchema.optional(),
    ma60: PeriodDataSchema.optional(),
    ma120: PeriodDataSchema.optional(),
  }),
}).passthrough();

// schema 1.0: dapanyuntu 单 MA20 扁平结构
const V1Schema = z.object({
  schema_version: z.string(),
  dates: z.array(z.string()),
  market: z.array(MarketPointSchema),
  industries_l1: z.array(BreadthRowSchema),
  industries_l2: z.array(BreadthRowSchema),
}).passthrough();

/** 归一化后的统一形态: 无论 1.0/2.0, 都暴露 dates + 各周期数据 + 可用周期. */
export interface NormalizedTemperature {
  dates: string[];
  periods: Partial<Record<PeriodKey, PeriodData>>;
  /** 有数据(至少一个非 null market rate)的周期, 用于切换器可用性. */
  available: PeriodKey[];
}

const hasData = (p: PeriodData | undefined): boolean =>
  !!p && p.market.some((m) => m.rate !== null);

/** 解析原始快照 JSON → 归一化. 2.0 优先, 回退 1.0. */
export function normalizeMarketTemperature(raw: unknown): NormalizedTemperature {
  const v2 = V2Schema.safeParse(raw);
  if (v2.success && v2.data.periods) {
    const periods = v2.data.periods as Partial<Record<PeriodKey, PeriodData>>;
    return {
      dates: v2.data.dates,
      periods,
      available: PERIOD_KEYS.filter((k) => hasData(periods[k])),
    };
  }
  const v1 = V1Schema.parse(raw); // 抛错交给 SWR
  const ma20: PeriodData = {
    market: v1.market,
    industries_l1: v1.industries_l1,
    industries_l2: v1.industries_l2,
  };
  return { dates: v1.dates, periods: { ma20 }, available: hasData(ma20) ? ['ma20'] : [] };
}
