import { z } from 'zod';
import { ReturnsSchema, StrengthSchema } from './themes';

export const EtfSchema = z.object({
  code: z.string(),
  name: z.string(),
  tracking_index: z.string(),
  theme_id: z.string().optional(),  // 后端 schema 1.x 后开始填; 历史 snapshot 可缺
  returns: ReturnsSchema,
  amount_yi: z.number().nonnegative().nullable(),  // 亿元成交额, 不为负
  price: z.number().positive().nullable(),  // ETF 价格必须 > 0
  strength: StrengthSchema,
});
export type Etf = z.infer<typeof EtfSchema>;

export const EtfsFileSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  etfs: z.array(EtfSchema),
});
export type EtfsFile = z.infer<typeof EtfsFileSchema>;
