// frontend/src/lib/subscription/types.ts
// 订阅相关类型（对应 Supabase subscriptions 表）

import { z } from 'zod';

export const PlanSchema = z.enum(['monthly', 'yearly']);
export type Plan = z.infer<typeof PlanSchema>;

export const SubscriptionSchema = z.object({
  id:                 z.string().uuid(),
  user_id:            z.string().uuid(),
  plan:               PlanSchema,
  status:             z.enum(['active', 'inactive', 'expired']),
  current_period_end: z.string().nullable(),
  source:             z.string(),
  afdian_trade_no:    z.string().nullable(),
  created_at:         z.string(),
  updated_at:         z.string(),
});
export type Subscription = z.infer<typeof SubscriptionSchema>;

// useSubscription 对外四态：loading（拉取中）/ member（生效会员）/
// non-member（未订阅或已过期）/ error（查询失败或行形状异常 —— 不得与未订阅混淆,
// 否则基础设施故障时生效会员会被静默锁功能）
export type SubscriptionState = 'loading' | 'member' | 'non-member' | 'error';

export interface UseSubscriptionResult {
  state:     SubscriptionState;
  plan:      Plan | null;
  periodEnd: string | null;   // ISO 到期时间；非会员为 null
  refresh:   () => Promise<void>;
}
