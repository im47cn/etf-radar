import type { RotationPoint, Quadrant, HealthGrade, HealthScore } from '@/types/rotation';
import type { Theme } from '@/types/themes';
import { themesToRotationPoints, type RotationMode } from './rotation';

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

/**
 * 档位阈值: 基于历史快照实测分位数, 按市场分别标定. 详见 spec §10.
 * - us: 123 个有效快照 (us_strength)
 * - cn: 127 个有效快照 (cn_strength, A 股主题更多, 覆盖度分布右移)
 */
const HEALTH_THRESHOLDS: Record<RotationMode, {
  coverage: { p50: number; p25: number };
  robustness: { p50: number; p25: number };
}> = {
  us: {
    coverage: { p50: 80, p25: 74 },
    robustness: { p50: 77, p25: 69 },
  },
  cn: {
    coverage: { p50: 89, p25: 81 },
    robustness: { p50: 75, p25: 71 },
  },
};

/**
 * 覆盖度档位: 按 mode 选择历史 P25/P50 作为切分点.
 */
export function gradeCoverage(
  score: number,
  n: number,
  mode: RotationMode = 'us',
): HealthGrade {
  if (n < 2) return 'insufficient';
  const { p50, p25 } = HEALTH_THRESHOLDS[mode].coverage;
  if (score >= p50) return 'healthy';
  if (score >= p25) return 'caution';
  return 'imbalanced';
}

/**
 * 鲁棒度档位: 按 mode 选择历史 P25/P50 作为切分点.
 */
export function gradeRobustness(
  score: number,
  n: number,
  mode: RotationMode = 'us',
): HealthGrade {
  if (n < 1) return 'insufficient';
  const { p50, p25 } = HEALTH_THRESHOLDS[mode].robustness;
  if (score >= p50) return 'healthy';
  if (score >= p25) return 'caution';
  return 'imbalanced';
}

/**
 * 一站式入口: 主题数组 → 完整 HealthScore. 分数取整, 档位由 grade* 函数判定.
 * mode 决定使用 us_strength 还是 cn_strength, 默认 'us' 兼容老调用.
 * 档位阈值按 mode 分别标定 (见 HEALTH_THRESHOLDS).
 */
export function computeRotationHealth(
  themes: Theme[],
  mode: RotationMode = 'us',
): HealthScore {
  const points = themesToRotationPoints(themes, mode);
  const n = points.length;

  const coverageScore = Math.round(computeCoverage(points));
  const robustnessScore = Math.round(computeRobustness(points));

  return {
    coverage: {
      score: coverageScore,
      grade: gradeCoverage(coverageScore, n, mode),
    },
    robustness: {
      score: robustnessScore,
      grade: gradeRobustness(robustnessScore, n, mode),
    },
  };
}
