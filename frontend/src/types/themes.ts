import { z } from 'zod';

export const DimNameSchema = z.enum(['short', 'mid', 'long', 'composite']);
export type DimName = z.infer<typeof DimNameSchema>;

export const ReturnsSchema = z.object({
  r_1d: z.number().nullable(),
  r_5d: z.number().nullable(),
  r_20d: z.number().nullable(),
  r_60d: z.number().nullable(),
  r_120d: z.number().nullable(),
  r_ytd: z.number().nullable(),
});
export type Returns = z.infer<typeof ReturnsSchema>;

export const StrengthSchema = z.object({
  short: z.number(),
  mid: z.number(),
  long: z.number(),
  composite: z.number(),
});
export type Strength = z.infer<typeof StrengthSchema>;

export const RankSchema = z.object({
  short: z.number(),
  mid: z.number(),
  long: z.number(),
  composite: z.number(),
});
export type Rank = z.infer<typeof RankSchema>;

export const ThemeSchema = z.object({
  id: z.string(),
  name: z.string(),
  us_etfs: z.array(z.string()),
  primary_us: z.string(),
  tags: z.array(z.string()),
  note: z.string(),
  returns: ReturnsSchema,
  strength: StrengthSchema,
  rank: RankSchema,
});
export type Theme = z.infer<typeof ThemeSchema>;

export const ThemesFileSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  themes: z.array(ThemeSchema),
});
export type ThemesFile = z.infer<typeof ThemesFileSchema>;
