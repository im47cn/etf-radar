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

// useSubscription 对外三态：loading（拉取中）/ member（生效会员）/ non-member（未订阅或已过期）
export type SubscriptionState = 'loading' | 'member' | 'non-member';

export interface UseSubscriptionResult {
  state:     SubscriptionState;
  plan:      Plan | null;
  periodEnd: string | null;   // ISO 到期时间；非会员为 null
  refresh:   () => Promise<void>;
}
