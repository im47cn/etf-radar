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
  /** 命中的主题 id 集合（用于现有页 ⭐/金圈叠加 + Phase 2 排除） */
  ownedThemeIds: Set<string>;
  /** 全市场主题（Phase 2 机会扫描的输入；已转换为 engine 友好的 ThemeMetric 形态） */
  themes: ThemeMetric[];
}

export function usePortfolioScores(): UsePortfolioScoresResult {
  const { holdings, loading } = useHoldings();
  const data = useDataContext();

  // data.themes: ThemesFile = { themes: Theme[] }
  // engine 现按 theme_id 反查, 不再依赖 primary_cn 索引;
  // primary_cn 字段保留兼容 ThemeMetric 类型定义, 缺则空串
  const themes: ThemeMetric[] = useMemo(() => {
    if (!data?.themes) return [];
    return data.themes.themes.map((t) => ({
      id:          t.id,
      name:        t.name,
      primary_cn:  t.primary_cn ?? '',
      strength:    t.strength,
      us_strength: t.us_strength ?? undefined,
      cn_strength: t.cn_strength ?? undefined,
    }));
  }, [data]);

  const scores = useMemo(() => {
    if (!data?.themes || !data?.etfs) return [];

    // data.etfs: EtfsFile = { etfs: Etf[] }
    // price 可空 → 仅保留有价格的 ETF（无价无法算市值/盈亏）
    const etfs: EtfMetric[] = data.etfs.etfs
      .filter((e) => e.price !== null)
      .map((e) => ({
        code:           e.code,
        name:           e.name,
        tracking_index: e.tracking_index,
        theme_id:       e.theme_id,
        theme_ids:      e.theme_ids,   // 1:N 全部归属（含主），engine 用于次要归属
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
  }, [holdings, data, themes]);

  const ownedThemeIds = useMemo(() => {
    const set = new Set<string>();
    for (const s of scores) {
      if (s.themeId) set.add(s.themeId);
    }
    return set;
  }, [scores]);

  return { scores, loading, ownedThemeIds, themes };
}
