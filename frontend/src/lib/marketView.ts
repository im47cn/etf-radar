import type { Theme, Strength } from '@/types/themes';
import type { RotationMode } from '@/lib/rotation';

export type MarketView = 'us' | 'cn-all' | 'cn-only';

export const isCnOnly = (t: Theme): boolean => t.primary_us === null;

export const pickStrength = (t: Theme, mv: MarketView): Strength | null =>
  mv === 'us' ? t.us_strength : t.cn_strength;

export const themeMatchesView = (t: Theme, mv: MarketView): boolean => {
  if (mv === 'us') return !isCnOnly(t);
  if (mv === 'cn-only') return isCnOnly(t);
  return true; // cn-all
};

export const marketViewToRotationMode = (mv: MarketView): RotationMode =>
  mv === 'us' ? 'us' : 'cn';
