// frontend/src/lib/trading/api.ts
// supabase-js 直连 CRUD（照 HoldingsProvider 读写模式）
// 读：未登录/未配置返回空（settings 返回默认值）；DB 错抛 TradingApiError
// 写：统一返回 { error }（hook 惯例，UI 可直接展示）

import { z } from 'zod';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import {
  TradeSchema,
  TradeReviewSchema,
  TradingSettingsSchema,
  DEFAULT_SETTINGS_VALUES,
  TradingApiError,
  type Trade,
  type TradeReview,
  type TradeInput,
  type TradingSettings,
  type SettingsInput,
} from './types';

// 坏行静默过滤（同 HoldingsProvider / useWatchlist 惯例：zod 前向兼容历史行）
function parseRows<T>(rows: unknown[], schema: z.ZodType<T>): T[] {
  const out: T[] = [];
  for (const r of rows) {
    const p = schema.safeParse(r);
    if (p.success) out.push(p.data);
  }
  return out;
}

// ========== trades ==========

export async function listTrades(userId: string | null): Promise<Trade[]> {
  if (!userId || !isSupabaseConfigured()) return [];
  const { data, error } = await getSupabase()
    .from('trades')
    .select('*')
    .order('trade_date', { ascending: true })
    .order('created_at', { ascending: true });
  if (error) throw new TradingApiError('db', error.message);
  return parseRows(data ?? [], TradeSchema);
}

export async function insertTrade(userId: string | null, input: TradeInput): Promise<{ error: string | null }> {
  if (!userId) return { error: '未登录' };
  if (!isSupabaseConfigured()) return { error: 'Supabase 未配置' };
  const { error } = await getSupabase().from('trades').insert({
    user_id:    userId,
    code:       input.code,
    name:       input.name,
    side:       input.side,
    trade_date: input.trade_date,
    price:      input.price,
    shares:     input.shares,
    stop_after: input.stop_after ?? null,
    reason:     input.reason ?? null,
  });
  return { error: error ? error.message : null };
}

// 删除错录的交易（事件流回放即回滚其影响）
export async function deleteTrade(userId: string | null, id: string): Promise<{ error: string | null }> {
  if (!userId) return { error: '未登录' };
  if (!isSupabaseConfigured()) return { error: 'Supabase 未配置' };
  const { error } = await getSupabase()
    .from('trades')
    .delete()
    .eq('id', id);
  return { error: error ? error.message : null };
}

// ========== trade_reviews（M4 Actions 写入，此处仅本人读取） ==========

export async function listReviews(userId: string | null): Promise<TradeReview[]> {
  if (!userId || !isSupabaseConfigured()) return [];
  const { data, error } = await getSupabase()
    .from('trade_reviews')
    .select('*')
    .order('computed_at', { ascending: false });
  if (error) throw new TradingApiError('db', error.message);
  return parseRows(data ?? [], TradeReviewSchema);
}

// ========== trading_settings ==========

export async function getSettings(userId: string | null): Promise<TradingSettings> {
  if (!userId || !isSupabaseConfigured()) {
    return { user_id: userId ?? '', updated_at: '', ...DEFAULT_SETTINGS_VALUES };
  }
  const { data, error } = await getSupabase()
    .from('trading_settings')
    .select('*')
    .eq('user_id', userId)
    .maybeSingle();
  if (error) throw new TradingApiError('db', error.message);
  // 无行 → 默认值；行损坏 → 同样回退默认值（不炸 UI）
  const parsed = data ? TradingSettingsSchema.safeParse(data) : null;
  return parsed?.success
    ? parsed.data
    : { user_id: userId, updated_at: '', ...DEFAULT_SETTINGS_VALUES };
}

export async function saveSettings(
  userId: string | null,
  patch: SettingsInput,
): Promise<{ error: string | null }> {
  if (!userId) return { error: '未登录' };
  if (!isSupabaseConfigured()) return { error: 'Supabase 未配置' };
  const { error } = await getSupabase()
    .from('trading_settings')
    .upsert({ user_id: userId, ...patch }, { onConflict: 'user_id' });
  return { error: error ? error.message : null };
}
