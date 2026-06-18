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

/**
 * 距边界 < EDGE_THRESHOLD 即视为脆弱: 小幅波动就会跨象限.
 * 设为 10 是首版默认 (strength 是 0-99 整数, ±10 约对应一日 ±1% 收益的强度抖动).
 */
export const EDGE_THRESHOLD = 10;

/**
 * 鲁棒度: 远离边界线 (x=50 或 y=50) 超过 EDGE_THRESHOLD 单位的主题占比 * 100.
 * 100 = 没有脆弱主题, 0 = 全部脆弱.
 * N = 0 时返回 0.
 */
export function computeRobustness(points: RotationPoint[]): number {
  if (points.length === 0) return 0;

  let fragileCount = 0;
  for (const p of points) {
    const xNearEdge = Math.abs(p.x - 50) < EDGE_THRESHOLD;
    const yNearEdge = Math.abs(p.y - 50) < EDGE_THRESHOLD;
    if (xNearEdge || yNearEdge) fragileCount++;
  }
  return (1 - fragileCount / points.length) * 100;
}
