// frontend/src/hooks/usePortfolioScores.ts
//
// 组合 useHoldings + useData，输出每个持仓的融合评分。
// 不做新 IO，只是把 DataProvider 已有 JSON 喂给 scorePortfolio。

import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useHoldings } from './useHoldings';
import { scorePortfolio } from '@/lib/portfolio/engine';
import type {
  HoldingScore,
  ThemeMetric,
  EtfMetric,
  ThemeSignalEntry,
} from '@/lib/portfolio/types';

export interface UsePortfolioScoresResult {
  scores: HoldingScore[];
  loading: boolean;
  /** 命中的主题 id 集合（用于现有页 ⭐/金圈叠加） */
  ownedThemeIds: Set<string>;
}

export function usePortfolioScores(): UsePortfolioScoresResult {
  const { holdings, loading } = useHoldings();
  const data = useDataContext();

  const scores = useMemo(() => {
    if (!data?.themes || !data?.etfs) return [];

    // data.themes: ThemesFile = { themes: Theme[] }
    // primary_cn 可空 → 仅保留有 A 股映射的主题；us_strength/cn_strength 可空 → ?? undefined
    const themes: ThemeMetric[] = data.themes.themes
      .filter((t) => t.primary_cn !== null)
      .map((t) => ({
        id:          t.id,
        name:        t.name,
        primary_cn:  t.primary_cn!,
        strength:    t.strength,
        us_strength: t.us_strength ?? undefined,
        cn_strength: t.cn_strength ?? undefined,
      }));

    // data.etfs: EtfsFile = { etfs: Etf[] }
    // price 可空 → 仅保留有价格的 ETF（无价无法算市值/盈亏）
    const etfs: EtfMetric[] = data.etfs.etfs
      .filter((e) => e.price !== null)
      .map((e) => ({
        code:           e.code,
        name:           e.name,
        tracking_index: e.tracking_index,
        price:          e.price!,
        strength:       e.strength,
      }));

    // data.signals: SignalsFile = { theme_signals: ThemeSignal[] }
    // signal 可空 → 过滤无信号项
    const themeSignals: ThemeSignalEntry[] = (data.signals?.theme_signals ?? [])
      .filter((s) => s.signal !== null)
      .map((s) => ({
        theme_id: s.theme_id,
        signal:   s.signal!,
      }));

    return scorePortfolio({ holdings, themes, etfs, themeSignals });
  }, [holdings, data]);

  const ownedThemeIds = useMemo(() => {
    const set = new Set<string>();
    for (const s of scores) {
      if (s.themeId) set.add(s.themeId);
    }
    return set;
  }, [scores]);

  return { scores, loading, ownedThemeIds };
}
