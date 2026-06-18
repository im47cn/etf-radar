import type { RotationPoint, Quadrant } from '@/types/rotation';

/**
 * 覆盖度: 四象限主题数的香农熵, 归一到 0-100.
 * 100 = 四象限完全均匀, 0 = 全部挤在一个象限.
 * N < 2 时无意义, 返回 0 (调用方应配合 gradeCoverage 判定为 insufficient).
 */
export function computeCoverage(points: RotationPoint[]): number {
  if (points.length < 2) return 0;

  const counts: Record<Quadrant, number> = {
    leading: 0,
    rising: 0,
    lagging: 0,
    fading: 0,
  };
  for (const p of points) counts[p.quadrant]++;

  const total = points.length;
  let H = 0;
  for (const c of Object.values(counts)) {
    if (c === 0) continue; // 数学约定: 0 * log(0) := 0
    const p = c / total;
    H -= p * Math.log2(p);
  }
  return (H / Math.log2(4)) * 100;
}
