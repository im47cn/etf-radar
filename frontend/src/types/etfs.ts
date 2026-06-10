import { z } from 'zod';
import { ReturnsSchema, StrengthSchema } from './themes';

export const EtfSchema = z.object({
  code: z.string(),
  name: z.string(),
  tracking_index: z.string(),
  returns: ReturnsSchema,
  amount_yi: z.number().nullable(),
  price: z.number().nullable(),
  strength: StrengthSchema,
});
export type Etf = z.infer<typeof EtfSchema>;

export const EtfsFileSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  etfs: z.array(EtfSchema),
});
export type EtfsFile = z.infer<typeof EtfsFileSchema>;
