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
    try {
      const { data, error } = await getSupabase()
        .from('subscriptions')
        .select('*')
        .eq('user_id', user.id)
        .maybeSingle();

      // 查询错误与「无订阅」必须可区分: 混同会让网络/RLS 故障时
      // 生效会员被静默锁功能且无任何提示 (2026-09-27 审查 P1)。
      if (error) {
        setPlan(null);
        setPeriodEnd(null);
        setState('error');
        return;
      }
      if (!data) {
        setPlan(null);
        setPeriodEnd(null);
        setState('non-member');
        return;
      }
      const parsed = SubscriptionSchema.safeParse(data);
      if (!parsed.success) {
        setPlan(null);
        setPeriodEnd(null);
        setState('error');
        return;
      }
      const sub = parsed.data;
      setPlan(sub.plan);
      setPeriodEnd(sub.current_period_end);
      setState(isActive(sub.status, sub.current_period_end) ? 'member' : 'non-member');
    } catch {
      // 网络异常等 throw: 同样走 error 而非降级 non-member
      setPlan(null);
      setPeriodEnd(null);
      setState('error');
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
