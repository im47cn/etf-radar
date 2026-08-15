import { z } from 'zod';

export const SignalTypeSchema = z.enum(['resonance', 'transmission', 'divergence']);
export type SignalType = z.infer<typeof SignalTypeSchema>;

export const VotesSchema = z.object({
  short: SignalTypeSchema.nullable(),
  mid: SignalTypeSchema.nullable(),
  long: SignalTypeSchema.nullable(),
});
export type Votes = z.infer<typeof VotesSchema>;

export const DirectionSchema = z.enum(['up', 'down']);
export type Direction = z.infer<typeof DirectionSchema>;

export const ThemeSignalSchema = z.object({
  theme_id: z.string(),
  signal: SignalTypeSchema.nullable(),
  // 方向取美股 short 收益符号; 历史快照缺省→null (仅 resonance 有统计意义)
  direction: DirectionSchema.nullish().transform((v) => v ?? null),
  // 方向置信档 (样本外验证): high=|动量|≥1% 同向57% / low=<0.3%≈随机 / null=中间档
  direction_tier: z.enum(['high', 'low']).nullish().transform((v) => v ?? null),
  trigger_cn_etf: z.string().nullable(),
  votes: VotesSchema,
  description: z.string(),
});
export type ThemeSignal = z.infer<typeof ThemeSignalSchema>;

export const PairSignalSchema = z.object({
  theme_id: z.string(),
  cn_code: z.string(),
  mapping_score: z.number().int().min(0).max(100).nullable(),  // 0-100 整数
  confidence: z.number().int().min(0).max(100),  // hardcode 档: 60 or 90
  signal: SignalTypeSchema.nullable(),
  votes: VotesSchema,
});
export type PairSignal = z.infer<typeof PairSignalSchema>;

export const SignalsFileSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  theme_signals: z.array(ThemeSignalSchema),
  pair_signals: z.array(PairSignalSchema),
});
export type SignalsFile = z.infer<typeof SignalsFileSchema>;
