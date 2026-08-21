import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { useAuth } from '@/hooks/useAuth';
import { listTrades, insertTrade, deleteTrade, editTrade as editTradeApi, getSettings, saveSettings } from '@/lib/trading/api';
import { derivePositions } from '@/lib/trading/derivePositions';
import {
  DEFAULT_SETTINGS_VALUES,
  type Position,
  type Trade,
  type TradeInput,
  type TradingSettings,
  type SettingsInput,
} from '@/lib/trading/types';

export interface UseTradesResult {
  trades:    Trade[];
  positions: Position[];       // 由 trades 事件流推导（open/add 累加、reduce/close 扣减）
  settings:  TradingSettings;  // 无行/未配置时为默认值
  loading:   boolean;
  error:     string | null;
  addTrade:       (input: TradeInput) => Promise<{ error: string | null }>;
  removeTrade:    (id: string) => Promise<{ error: string | null }>;
  editTrade:      (id: string, input: TradeInput) => Promise<{ error: string | null }>;
  updateSettings: (patch: SettingsInput) => Promise<{ error: string | null }>;
  refresh:  () => Promise<void>;
}

// 必须单例（同 HoldingsContext 理由）：supabase-js channel('name') 是同名单例，
// 多 hook 实例第二次 .on() 会抛 "cannot add postgres_changes callbacks after
// subscribe()" → 整页白屏。在 App 顶层挂一份 Provider，组件经 useTrades() 消费。
// eslint-disable-next-line react-refresh/only-export-components -- context 与 Provider 同文件是 Lane M3 文件所有权约束 (不另建 tradesContext.ts), 仅 useTrades 消费
export const TradesContext = createContext<UseTradesResult | null>(null);

function useTradesImpl(): UseTradesResult {
  const { user, status } = useAuth();
  const [trades, setTrades]           = useState<Trade[]>([]);
  const [settings, setSettings]       = useState<TradingSettings>({
    user_id: '', updated_at: '', ...DEFAULT_SETTINGS_VALUES,
  });
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user || !isSupabaseConfigured()) {
      setTrades([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [ts, st] = await Promise.all([listTrades(user.id), getSettings(user.id)]);
      setTrades(ts);
      setSettings(st);
    } catch (e) {
      // listTrades/getSettings 抛 TradingApiError（类型化），此处降级为可展示消息
      setError(e instanceof Error ? e.message : String(e));
      setTrades([]);
    } finally {
      setLoading(false);
    }
  }, [user]);

  // refresh 引用持 ref，避免 realtime effect 在 user 变化时重跑（同 HoldingsProvider）
  const refreshRef = useRef(refresh);
  useEffect(() => { refreshRef.current = refresh; }, [refresh]);

  useEffect(() => {
    if (status === 'authenticated') refreshRef.current();
  }, [status]);

  // Realtime 订阅 trades 表（settings 为本人单行低频数据，手动保存后 refresh 即可）。
  // removeChannel 真正销毁 channel，防同名单例残留 → 白屏。
  useEffect(() => {
    if (status !== 'authenticated' || !isSupabaseConfigured()) return;
    const supabase = getSupabase();
    const channel = supabase
      .channel('trades_changes')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'trades' }, () => {
        refreshRef.current();
      })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [status]);

  const positions = useMemo(() => derivePositions(trades), [trades]);

  const addTrade = useCallback(async (input: TradeInput) => {
    if (!user) return { error: '未登录' };
    const r = await insertTrade(user.id, input);
    if (!r.error) await refresh();
    return r;
  }, [user, refresh]);

  const removeTrade = useCallback(async (id: string) => {
    if (!user) return { error: '未登录' };
    const r = await deleteTrade(user.id, id);
    if (!r.error) await refresh();
    return r;
  }, [user, refresh]);

  const editTrade = useCallback(async (id: string, input: TradeInput) => {
    if (!user) return { error: '未登录' };
    const r = await editTradeApi(user.id, id, input);
    if (!r.error) await refresh();
    return r;
  }, [user, refresh]);

  const updateSettings = useCallback(async (patch: SettingsInput) => {
    if (!user) return { error: '未登录' };
    const r = await saveSettings(user.id, patch);
    if (!r.error) await refresh();
    return r;
  }, [user, refresh]);

  const isAuthed = status === 'authenticated';
  return {
    trades:    isAuthed ? trades : [],
    positions: isAuthed ? positions : [],
    settings:  isAuthed ? settings : { user_id: '', updated_at: '', ...DEFAULT_SETTINGS_VALUES },
    loading:   isAuthed ? loading : false,
    error,
    addTrade,
    removeTrade,
    editTrade,
    updateSettings,
    refresh,
  };
}

export function TradesProvider({ children }: { children: ReactNode }) {
  const value = useTradesImpl();
  return <TradesContext.Provider value={value}>{children}</TradesContext.Provider>;
}
