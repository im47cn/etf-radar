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

// Backend Pydantic uses Field(ge=0, le=100). Implementation clamps to 99
// (留 100 给"完美样本"). Allow 0..99 here; if backend ever emits 100 it'll error.
const StrengthScore = z.number().int().min(0).max(99);

export const StrengthSchema = z.object({
  short: StrengthScore,
  mid: StrengthScore,
  long: StrengthScore,
  composite: StrengthScore,
});
export type Strength = z.infer<typeof StrengthSchema>;

// Rank 1..N (theme 池大小, 当前 14). 严格要求正整数.
const RankPosition = z.number().int().positive();

export const RankSchema = z.object({
  short: RankPosition,
  mid: RankPosition,
  long: RankPosition,
  composite: RankPosition,
});
export type Rank = z.infer<typeof RankSchema>;

export const ThemeSchema = z.object({
  id: z.string(),
  name: z.string(),
  us_etfs: z.array(z.string()),
  primary_us: z.string().nullable(),
  primary_cn: z.string().nullable(),
  tags: z.array(z.string()),
  note: z.string(),
  returns: ReturnsSchema,
  strength: StrengthSchema,
  us_strength: StrengthSchema.nullable(),
  cn_strength: StrengthSchema.nullable(),
  rank: RankSchema,
});
export type Theme = z.infer<typeof ThemeSchema>;

export const ThemesFileSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  themes: z.array(ThemeSchema),
});
export type ThemesFile = z.infer<typeof ThemesFileSchema>;
