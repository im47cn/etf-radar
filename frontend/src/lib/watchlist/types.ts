// frontend/src/lib/watchlist/types.ts
// 自选盯盘类型（对应 Supabase watchlist 表）

import { z } from 'zod';

export const WatchItemTypeSchema = z.enum(['theme', 'etf']);
export type WatchItemType = z.infer<typeof WatchItemTypeSchema>;

export const WatchlistItemSchema = z.object({
  id:         z.string().uuid(),
  user_id:    z.string().uuid(),
  item_type:  WatchItemTypeSchema,
  item_key:   z.string(),
  created_at: z.string(),
});
export type WatchlistItem = z.infer<typeof WatchlistItemSchema>;

// add 遇到 RPC 抛出的 NOT_A_MEMBER 时，包装为可识别错误供 UI 提示"需会员"。
export class NotAMemberError extends Error {
  constructor() {
    super('NOT_A_MEMBER');
    this.name = 'NotAMemberError';
  }
}

export interface UseWatchlistResult {
  items:   WatchlistItem[];
  loading: boolean;
  error:   string | null;
  refresh: () => Promise<void>;
  add:     (itemType: WatchItemType, itemKey: string) => Promise<{ error: string | null }>;
  remove:  (id: string) => Promise<{ error: string | null }>;
}
