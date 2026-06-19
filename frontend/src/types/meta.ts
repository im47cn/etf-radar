import { z } from 'zod';

export const ProviderStatusSchema = z.enum(['ok', 'fallback', 'degraded', 'stale']);
export type ProviderStatus = z.infer<typeof ProviderStatusSchema>;

export const ProviderInfoSchema = z.object({
  status: ProviderStatusSchema,
  name: z.string(),
});
export type ProviderInfo = z.infer<typeof ProviderInfoSchema>;

export const MetaFileSchema = z.object({
  schema_version: z.string(),
  last_full_refresh: z.object({
    us: z.string().nullable(),
    cn: z.string().nullable(),
  }),
  last_intraday_refresh: z.string().nullable(),
  providers: z.object({
    us: ProviderInfoSchema,
    cn: ProviderInfoSchema,
  }),
  failed_symbols: z.array(z.string()),
  fallback_symbols: z.record(z.string(), z.string()).default({}),
  stale_minutes: z.number().int().nonnegative(),
  calendar: z.object({
    us_trading_today: z.boolean(),
    cn_trading_today: z.boolean(),
    us_session_active: z.boolean(),
    cn_session_active: z.boolean(),
  }),
});
export type MetaFile = z.infer<typeof MetaFileSchema>;
