import { z } from 'zod';

export const SignalTypeSchema = z.enum(['resonance', 'transmission', 'divergence']);
export type SignalType = z.infer<typeof SignalTypeSchema>;

export const VotesSchema = z.object({
  short: SignalTypeSchema.nullable(),
  mid: SignalTypeSchema.nullable(),
  long: SignalTypeSchema.nullable(),
});
export type Votes = z.infer<typeof VotesSchema>;

export const TopThemeSchema = z.object({
  id: z.string(),
  name: z.string(),
  primary_us: z.string(),
  composite_strength: z.number(),
});
export type TopTheme = z.infer<typeof TopThemeSchema>;

export const SignalsSummarySchema = z.object({
  themes_total: z.number(),
  etfs_total: z.number(),
  resonance_count: z.number(),
  transmission_count: z.number(),
  divergence_count: z.number(),
  top_theme: TopThemeSchema.nullable(),
});
export type SignalsSummary = z.infer<typeof SignalsSummarySchema>;

export const ThemeSignalSchema = z.object({
  theme_id: z.string(),
  signal: SignalTypeSchema.nullable(),
  trigger_cn_etf: z.string().nullable(),
  votes: VotesSchema,
  description: z.string(),
});
export type ThemeSignal = z.infer<typeof ThemeSignalSchema>;

export const PairSignalSchema = z.object({
  theme_id: z.string(),
  cn_code: z.string(),
  mapping_score: z.number().nullable(),
  confidence: z.number(),
  signal: SignalTypeSchema.nullable(),
  votes: VotesSchema,
});
export type PairSignal = z.infer<typeof PairSignalSchema>;

export const SignalsFileSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  summary: SignalsSummarySchema,
  theme_signals: z.array(ThemeSignalSchema),
  pair_signals: z.array(PairSignalSchema),
});
export type SignalsFile = z.infer<typeof SignalsFileSchema>;
