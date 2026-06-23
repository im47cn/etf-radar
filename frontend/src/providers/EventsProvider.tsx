import { useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { useAuth } from '@/hooks/useAuth';
import type { UserEvent, PendingEvent } from '@/lib/portfolio/eventTypes';
import { UserEventSchema } from '@/lib/portfolio/eventTypes';
import { EventsContext, type UseEventsResult } from './eventsContext';

/** spec §5.5 验收：90 天前事件不显示 */
const SHOW_DAYS = 90;

function within90Days(iso: string): boolean {
  const created = Date.parse(iso);
  if (Number.isNaN(created)) return false;
  return Date.now() - created < SHOW_DAYS * 86400_000;
}

function useEventsImpl(): UseEventsResult {
  const { user, status } = useAuth();
  const [events, setEvents] = useState<UserEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user || !isSupabaseConfigured()) {
      setEvents([]);
      return;
    }
    setLoading(true);
    setError(null);
    const { data, error } = await getSupabase()
      .from('user_events')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(200);
    if (error) {
      setError(error.message);
      setEvents([]);
    } else {
      // 对 DB payload 做 Zod 安全校验，过滤畸形行，避免消费方运行时崩溃
      const parsed = (data ?? [])
        .map(r => UserEventSchema.safeParse(r))
        .filter(p => p.success)
        .map(p => p.data!);
      setEvents(parsed);
    }
    setLoading(false);
  }, [user]);

  // refresh 引用持 ref，避免下面两个 effect 在 user 变化时重跑
  // (Realtime 重跑会触发 'cannot add callbacks after subscribe()' → 白屏).
  // React 19 禁止 render 中改 ref，用 effect 同步.
  const refreshRef = useRef(refresh);
  useEffect(() => { refreshRef.current = refresh; }, [refresh]);

  // 初始拉取: refreshRef.current() 间接调用了 setLoading/setEvents，但这是从外部系统
  // (Supabase) 同步状态到 React 的合法用法，而非 effect-body 内的派生 state.
  useEffect(() => {
    if (status === 'authenticated') refreshRef.current();
  }, [status]);

  // Realtime 订阅 — channel by name（含 user.id 确保隔离）在 supabase-js 内是单例，
  // 必须 removeChannel 真正销毁，仅 unsubscribe 会留下 closed channel，
  // 下次 effect 拿到的还是它，.on() 会抛
  // "cannot add postgres_changes callbacks after subscribe()" → 整页白屏
  //
  // 依赖只取 user?.id（而非完整 user 对象）：避免 auth token refresh 导致 user 引用变化
  // 触发不必要的重订阅；effect 内部只用 userId 字符串，与 user 引用无关。
  const userId = user?.id;
  useEffect(() => {
    if (status !== 'authenticated' || !isSupabaseConfigured() || !userId) return;
    const supabase = getSupabase();
    const channel = supabase
      .channel(`user_events_${userId}`)
      .on('postgres_changes',
        { event: '*', schema: 'public', table: 'user_events', filter: `user_id=eq.${userId}` },
        () => { refreshRef.current(); })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [status, userId]);

  const upsertEvents = useCallback(async (pending: PendingEvent[]): Promise<{ inserted: number; error: string | null }> => {
    if (!user) return { inserted: 0, error: '未登录' };
    if (pending.length === 0) return { inserted: 0, error: null };
    const rows = pending.map(p => ({ ...p, user_id: user.id }));
    const { data, error } = await getSupabase()
      .from('user_events')
      .upsert(rows, { onConflict: 'user_id,event_signature', ignoreDuplicates: true })
      .select('id');
    if (error) return { inserted: 0, error: error.message };
    await refresh();
    return { inserted: data?.length ?? 0, error: null };
  }, [user, refresh]);

  const markRead = useCallback(async (eventIds: string[]) => {
    if (!user || eventIds.length === 0) return { error: null };
    const { error } = await getSupabase()
      .from('user_events')
      .update({ read_at: new Date().toISOString() })
      .in('id', eventIds)
      .is('read_at', null);
    if (error) return { error: error.message };
    await refresh();
    return { error: null };
  }, [user, refresh]);

  const markAllRead = useCallback(async () => {
    if (!user) return { error: null };
    const { error } = await getSupabase()
      .from('user_events')
      .update({ read_at: new Date().toISOString() })
      .eq('user_id', user.id)
      .is('read_at', null);
    if (error) return { error: error.message };
    await refresh();
    return { error: null };
  }, [user, refresh]);

  const visible = events.filter(e => within90Days(e.created_at));
  const unreadCount = visible.filter(e => e.read_at === null).length;

  const isAuthed = status === 'authenticated';
  return {
    events:      isAuthed ? visible : [],
    unreadCount: isAuthed ? unreadCount : 0,
    loading:     isAuthed ? loading : false,
    error,
    upsertEvents,
    markRead,
    markAllRead,
  };
}

export function EventsProvider({ children }: { children: ReactNode }) {
  const value = useEventsImpl();
  return <EventsContext.Provider value={value}>{children}</EventsContext.Provider>;
}
