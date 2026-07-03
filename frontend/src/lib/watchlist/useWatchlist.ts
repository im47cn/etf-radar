// frontend/src/lib/watchlist/useWatchlist.ts
// 会员自选盯盘 hook。list/remove 走表；add 走 add_watchlist RPC（服务端强制会员校验）。

import { useCallback, useEffect, useState } from 'react';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { useAuthOptional } from '@/hooks/useAuth';
import {
  WatchlistItemSchema,
  NotAMemberError,
  type WatchlistItem,
  type WatchItemType,
  type UseWatchlistResult,
} from './types';

export function useWatchlist(): UseWatchlistResult {
  const auth = useAuthOptional();
  const user = auth?.user ?? null;
  const status = auth?.status ?? 'unconfigured';
  const [items, setItems]     = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user || !isSupabaseConfigured()) {
      setItems([]);
      return;
    }
    setLoading(true);
    setError(null);
    const { data, error } = await getSupabase()
      .from('watchlist')
      .select('*')
      .order('created_at', { ascending: false });
    if (error) {
      setError(error.message);
      setItems([]);
    } else {
      const parsed = (data ?? [])
        .map(r => WatchlistItemSchema.safeParse(r))
        .filter(p => p.success)
        .map(p => p.data!);
      setItems(parsed);
    }
    setLoading(false);
  }, [user]);

  // refresh 内部 setState 是从 Supabase 同步状态到 React 的合法用法, 同 HoldingsProvider。
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (status === 'authenticated') void refresh();
    else setItems([]);
  }, [status, refresh]);

  const add = useCallback(async (itemType: WatchItemType, itemKey: string) => {
    if (!user) return { error: '未登录' };
    const { error } = await getSupabase().rpc('add_watchlist', {
      p_item_type: itemType,
      p_item_key:  itemKey,
    });
    if (error) {
      // RPC 内 RAISE EXCEPTION 'NOT_A_MEMBER' → 包装为可识别错误
      if (error.message.includes('NOT_A_MEMBER')) {
        throw new NotAMemberError();
      }
      return { error: error.message };
    }
    await refresh();
    return { error: null };
  }, [user, refresh]);

  const remove = useCallback(async (id: string) => {
    if (!user) return { error: '未登录' };
    const { error } = await getSupabase()
      .from('watchlist')
      .delete()
      .eq('id', id);
    if (error) return { error: error.message };
    await refresh();
    return { error: null };
  }, [user, refresh]);

  const isAuthed = status === 'authenticated';
  return {
    items:   isAuthed ? items : [],
    loading: isAuthed ? loading : false,
    error,
    refresh,
    add,
    remove,
  };
}
