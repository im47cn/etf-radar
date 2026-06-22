import { createContext } from 'react';
import type { Holding } from '@/lib/portfolio/types';

export interface UpsertInput {
  etf_code:   string;
  shares:     number;
  cost_price: number | null;
  note?:      string | null;
}

export interface UseHoldingsResult {
  holdings: Holding[];
  loading:  boolean;
  error:    string | null;
  upsert:   (input: UpsertInput) => Promise<{ error: string | null; merged?: boolean }>;
  remove:   (etfCode: string) => Promise<{ error: string | null }>;
  refresh:  () => Promise<void>;
}

// 必须单例: supabase-js channel('name') 是同名单例, 多 hook 实例第二次 .on()
// 会抛 "cannot add postgres_changes callbacks after subscribe()" → 整页白屏.
// useHoldings 被 HoldingsList / HoldingsEditor / usePortfolioScores 三处调用,
// usePortfolioScores 又用在 ThemeList / RotationPage, 必须在 App 顶层 Provider 共享一份.
export const HoldingsContext = createContext<UseHoldingsResult | null>(null);
