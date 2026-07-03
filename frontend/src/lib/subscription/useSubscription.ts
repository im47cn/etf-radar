// frontend/src/lib/subscription/useSubscription.ts
// 会员订阅状态 hook。仅用于 UX 门控，安全边界由 RLS / RPC 服务端强制。

import { useCallback, useEffect, useState } from 'react';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { useAuth } from '@/hooks/useAuth';
import { SubscriptionSchema, type UseSubscriptionResult, type SubscriptionState, type Plan } from './types';

// status=active 且 current_period_end 在未来 → 生效会员；到期自然回落。
function isActive(status: string, periodEnd: string | null): boolean {
  if (status !== 'active' || !periodEnd) return false;
  return new Date(periodEnd).getTime() > Date.now();
}

export function useSubscription(): UseSubscriptionResult {
  const { user, status } = useAuth();
  const [state, setState]         = useState<SubscriptionState>('loading');
  const [plan, setPlan]           = useState<Plan | null>(null);
  const [periodEnd, setPeriodEnd] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // 未登录 / 未配置 Supabase → 直接 non-member
    if (!user || !isSupabaseConfigured()) {
      setPlan(null);
      setPeriodEnd(null);
      setState('non-member');
      return;
    }
    setState('loading');
    const { data, error } = await getSupabase()
      .from('subscriptions')
      .select('*')
      .eq('user_id', user.id)
      .maybeSingle();

    if (error || !data) {
      setPlan(null);
      setPeriodEnd(null);
      setState('non-member');
      return;
    }
    const parsed = SubscriptionSchema.safeParse(data);
    if (!parsed.success) {
      setPlan(null);
      setPeriodEnd(null);
      setState('non-member');
      return;
    }
    const sub = parsed.data;
    if (isActive(sub.status, sub.current_period_end)) {
      setPlan(sub.plan);
      setPeriodEnd(sub.current_period_end);
      setState('member');
    } else {
      setPlan(sub.plan);
      setPeriodEnd(sub.current_period_end);
      setState('non-member');
    }
  }, [user]);

  // refresh 内部 setState 是从外部系统 (Supabase) 同步状态到 React 的合法用法,
  // 而非 effect-body 内派生 state; 与 HoldingsProvider 同款模式。
  useEffect(() => {
    // 认证态确定后拉取；loading 阶段保持 loading
    if (status === 'loading') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [status, refresh]);

  return { state, plan, periodEnd, refresh };
}
