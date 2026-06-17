import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

const OPACITY_MIN = 0.05;
const OPACITY_MAX = 0.4;

export function trailOpacity(i: number, total: number): number {
  if (total <= 1) return OPACITY_MAX;
  const t = i / (total - 1);
  return OPACITY_MIN + (OPACITY_MAX - OPACITY_MIN) * t;
}

export function pickTopByComposite(themes: Theme[], n: number): Set<string> {
  if (n <= 0) return new Set();
  const sorted = [...themes].sort((a, b) => b.strength.composite - a.strength.composite);
  return new Set(sorted.slice(0, n).map(t => t.id));
}

export interface TrailPoint {
  x: number;
  y: number;
  opacity: number;
  date: string;
}

export function buildTrails(
  frames: SnapshotFrame[],
  topN: Set<string>,
): Map<string, TrailPoint[]> {
  const result = new Map<string, TrailPoint[]>();
  const total = frames.length;
  for (const themeId of topN) {
    const points: TrailPoint[] = [];
    frames.forEach((frame, i) => {
      const theme = frame.themes.find(t => t.id === themeId);
      if (!theme) return;
      points.push({
        x: theme.strength.long,
        y: theme.strength.short,
        opacity: trailOpacity(i, total),
        date: frame.date,
      });
    });
    result.set(themeId, points);
  }
  return result;
}
