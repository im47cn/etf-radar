import { useEffect, useState, useCallback } from 'react';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { HoldingSchema, type Holding } from '@/lib/portfolio/types';
import { useAuth } from './useAuth';

export interface UseHoldingsResult {
  holdings: Holding[];
  loading:  boolean;
  error:    string | null;
  upsert:   (input: UpsertInput) => Promise<{ error: string | null; merged?: boolean }>;
  remove:   (etfCode: string) => Promise<{ error: string | null }>;
  refresh:  () => Promise<void>;
}

export interface UpsertInput {
  etf_code:   string;
  shares:     number;
  cost_price: number | null;
  note?:      string | null;
}

export function useHoldings(): UseHoldingsResult {
  const { user, status } = useAuth();
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user || !isSupabaseConfigured()) {
      setHoldings([]);
      return;
    }
    setLoading(true);
    setError(null);
    const { data, error } = await getSupabase()
      .from('user_holdings')
      .select('*')
      .order('created_at', { ascending: false });
    if (error) {
      setError(error.message);
      setHoldings([]);
    } else {
      const parsed = (data ?? [])
        .map(r => HoldingSchema.safeParse(r))
        .filter(p => p.success)
        .map(p => p.data!);
      setHoldings(parsed);
    }
    setLoading(false);
  }, [user]);

  // 初始拉取: refresh() 内部含 setLoading/setHoldings, 但这是从外部系统 (Supabase) 同步状态到 React 的合法用法,
  // 而非 effect-body 内的派生 state — 规则在此为假阳性.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (status === 'authenticated') refresh();
  }, [status, refresh]);

  // Realtime 订阅
  useEffect(() => {
    if (status !== 'authenticated' || !isSupabaseConfigured()) return;
    const sub = getSupabase()
      .channel('user_holdings_changes')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'user_holdings' }, () => {
        refresh();
      })
      .subscribe();
    return () => { sub.unsubscribe(); };
  }, [status, refresh]);

  // upsert：检测重复 → 合并加权平均成本
  const upsert = useCallback(async (input: UpsertInput) => {
    if (!user) return { error: '未登录' };

    const existing = holdings.find(h => h.etf_code === input.etf_code);
    let mergedShares = input.shares;
    let mergedCost   = input.cost_price;
    let merged       = false;

    if (existing) {
      merged = true;
      mergedShares = existing.shares + input.shares;
      // 加权平均成本（双方有 cost_price 才合并）
      if (existing.cost_price !== null && input.cost_price !== null) {
        mergedCost = (existing.cost_price * existing.shares + input.cost_price * input.shares) / mergedShares;
      } else {
        mergedCost = existing.cost_price ?? input.cost_price;
      }
    }

    const payload = {
      user_id:    user.id,
      etf_code:   input.etf_code,
      shares:     mergedShares,
      cost_price: mergedCost,
      note:       input.note ?? null,
    };

    const { error } = await getSupabase()
      .from('user_holdings')
      .upsert(payload, { onConflict: 'user_id,etf_code' });

    if (error) return { error: error.message };
    await refresh();
    return { error: null, merged };
  }, [user, holdings, refresh]);

  const remove = useCallback(async (etfCode: string) => {
    if (!user) return { error: '未登录' };
    const { error } = await getSupabase()
      .from('user_holdings')
      .delete()
      .eq('etf_code', etfCode);
    if (error) return { error: error.message };
    await refresh();
    return { error: null };
  }, [user, refresh]);

  // 派生: 非认证态对外暴露空列表/非加载, 避免 effect 同步 setState
  const isAuthed = status === 'authenticated';
  return {
    holdings: isAuthed ? holdings : [],
    loading:  isAuthed ? loading  : false,
    error,
    upsert,
    remove,
    refresh,
  };
}
