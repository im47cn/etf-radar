import type { Opportunity, ThemeMetric } from './types';
import { strengthTag, momentumTag } from './rules';

/** 强势综合分位阈值（含等于）。 */
export const COMPOSITE_MIN = 75;
/** 短周期分位阈值（含等于）— 配合 composite 过滤"近期发力"的主题。 */
export const SHORT_MIN = 70;
/** 候选列表截断条数。 */
export const MAX_OPPORTUNITIES = 10;

/**
 * 从全市场主题中筛出"未持有 + 当前信号偏强"的候选，按综合强度降序截前 10。
 *
 * 立场：仅做"信号事实陈述"，不输出任何买卖指令。文案在 UI 层用 L2 形容词标签呈现。
 */
export function scanOpportunities(
  themes: ThemeMetric[],
  ownedThemeIds: Set<string>,
): Opportunity[] {
  return themes
    .filter(t => !ownedThemeIds.has(t.id))
    .filter(t => t.strength.composite >= COMPOSITE_MIN)
    .filter(t => t.strength.short     >= SHORT_MIN)
    .sort((a, b) => b.strength.composite - a.strength.composite)
    .slice(0, MAX_OPPORTUNITIES)
    .map(t => ({
      themeId:     t.id,
      themeName:   t.name,
      primaryCn:   t.primary_cn,
      strength:    t.strength,
      l2Tag:       strengthTag(t.strength.composite),
      momentumTag: momentumTag(t.strength.short, t.strength.mid),
    }));
}
