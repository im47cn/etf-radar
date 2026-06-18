import type { SnapshotFrame } from '@/types/snapshots';

const OPACITY_MIN = 0.05;
const OPACITY_MAX = 0.4;

export function trailOpacity(i: number, total: number): number {
  if (total <= 1) return OPACITY_MAX;
  const t = i / (total - 1);
  return OPACITY_MIN + (OPACITY_MAX - OPACITY_MIN) * t;
}

export interface TrailPoint {
  x: number;
  y: number;
  opacity: number;
  date: string;
}

export interface BuildTrailsOptions {
  themeIds?: Set<string>;
}

export function buildTrails(
  frames: SnapshotFrame[],
  opts?: BuildTrailsOptions,
): Map<string, TrailPoint[]> {
  const result = new Map<string, TrailPoint[]>();
  const total = frames.length;
  if (total === 0) return result;

  let candidates: Set<string>;
  if (opts?.themeIds) {
    candidates = opts.themeIds;
  } else {
    candidates = new Set<string>();
    for (const frame of frames) {
      for (const theme of frame.themes) candidates.add(theme.id);
    }
  }

  for (const themeId of candidates) {
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
