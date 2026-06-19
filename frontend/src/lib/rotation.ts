import type { Theme } from '@/types/themes';
import type { Quadrant, RotationPoint } from '@/types/rotation';

const QUADRANT_THRESHOLD = 50;

/**
 * 气泡大小映射: composite (0-99) → 半径 (8-20px).
 * 8 是最小可见, 12 是 0→99 的增量斜率 (= 99/99 * 12).
 */
export const computeBubbleSize = (composite: number): number =>
  8 + (composite / 99) * 12;

export const QUADRANT_COLORS: Record<Quadrant, string> = {
  leading: '#10b981',
  rising:  '#3b82f6',
  lagging: '#6b7280',
  fading:  '#ef4444',
};

export const QUADRANT_LABELS: Record<Quadrant, string> = {
  leading: '持续强势',
  rising:  '新崛起',
  lagging: '持续弱势',
  fading:  '退潮',
};

export function classifyQuadrant(x: number, y: number): Quadrant {
  if (x >= QUADRANT_THRESHOLD && y >= QUADRANT_THRESHOLD) return 'leading';
  if (x <  QUADRANT_THRESHOLD && y >= QUADRANT_THRESHOLD) return 'rising';
  if (x <  QUADRANT_THRESHOLD && y <  QUADRANT_THRESHOLD) return 'lagging';
  return 'fading';
}

export type RotationMode = 'us' | 'cn';

export function themesToRotationPoints(
  themes: Theme[],
  mode: RotationMode = 'us',
): RotationPoint[] {
  const pickField = mode === 'us' ? 'us_strength' : 'cn_strength';
  return themes
    .map(t => {
      const s = t[pickField];
      if (!s) return null;
      return {
        themeId: t.id,
        themeName: t.name,
        x: s.long,
        y: s.short,
        size: s.composite,
        quadrant: classifyQuadrant(s.long, s.short),
        tags: t.tags,
      };
    })
    .filter((p): p is RotationPoint => p !== null);
}
