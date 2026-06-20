import type { SnapshotFrame } from '@/types/snapshots';
import type { RotationMode } from '@/lib/rotation';

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
  mode: RotationMode,
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

  const pickField = mode === 'us' ? 'us_strength' : 'cn_strength';

  for (const themeId of candidates) {
    const points: TrailPoint[] = [];
    frames.forEach((frame, i) => {
      const theme = frame.themes.find(t => t.id === themeId);
      if (!theme) return;
      // 优先取 mode-aware 字段; 若 us_strength 与 cn_strength **均** 为 null
      // (旧 schema 1.0 快照,不区分市场) 才回退到 strength;
      // 否则保留 null 语义 — cn-only 主题在 mode=us 时本帧应被跳过.
      const isLegacyFrame = theme.us_strength == null && theme.cn_strength == null;
      const s = isLegacyFrame ? theme.strength : theme[pickField];
      if (!s) return;
      points.push({
        x: s.long,
        y: s.short,
        opacity: trailOpacity(i, total),
        date: frame.date,
      });
    });
    // 全帧都被跳过 (cn-only + us) 时不写入 candidate.
    if (points.length > 0) result.set(themeId, points);
  }
  return result;
}
