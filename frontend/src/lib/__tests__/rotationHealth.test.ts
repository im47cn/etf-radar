import { describe, it, expect } from 'vitest';
import type { RotationPoint } from '@/types/rotation';
import { computeCoverage } from '../rotationHealth';

const mkPoint = (x: number, y: number, id = 't'): RotationPoint => ({
  themeId: id,
  themeName: id,
  x,
  y,
  size: 50,
  mid: 50,
  quadrant:
    x >= 50 && y >= 50 ? 'leading'
    : x < 50 && y >= 50 ? 'rising'
    : x < 50 && y < 50 ? 'lagging'
    : 'fading',
  tags: [],
});

describe('computeCoverage', () => {
  it('returns ~100 when all four quadrants are evenly populated', () => {
    const points = [
      mkPoint(80, 80, 'a1'), mkPoint(80, 80, 'a2'), mkPoint(80, 80, 'a3'),  // leading
      mkPoint(20, 80, 'b1'), mkPoint(20, 80, 'b2'), mkPoint(20, 80, 'b3'),  // rising
      mkPoint(20, 20, 'c1'), mkPoint(20, 20, 'c2'), mkPoint(20, 20, 'c3'),  // lagging
      mkPoint(80, 20, 'd1'), mkPoint(80, 20, 'd2'), mkPoint(80, 20, 'd3'),  // fading
    ];
    expect(computeCoverage(points)).toBeCloseTo(100, 0);
  });

  it('returns 0 when all points are in one quadrant', () => {
    const points = [
      mkPoint(80, 80, 'a1'), mkPoint(80, 80, 'a2'),
      mkPoint(80, 80, 'a3'), mkPoint(80, 80, 'a4'),
    ];
    expect(computeCoverage(points)).toBe(0);
  });

  it('returns 50 for bipolar distribution (2 quadrants equally)', () => {
    const points = [
      mkPoint(80, 80, 'a1'), mkPoint(80, 80, 'a2'), mkPoint(80, 80, 'a3'),
      mkPoint(20, 20, 'b1'), mkPoint(20, 20, 'b2'), mkPoint(20, 20, 'b3'),
    ];
    expect(computeCoverage(points)).toBeCloseTo(50, 1);
  });

  it('returns 0 for empty array', () => {
    expect(computeCoverage([])).toBe(0);
  });

  it('returns 0 for single point', () => {
    expect(computeCoverage([mkPoint(80, 80)])).toBe(0);
  });
});

import { computeRobustness, EDGE_THRESHOLD } from '../rotationHealth';

describe('computeRobustness', () => {
  it('returns 100 when all points are far from boundaries', () => {
    const points = [mkPoint(10, 10), mkPoint(10, 10), mkPoint(10, 10)];
    expect(computeRobustness(points)).toBe(100);
  });

  it('returns 0 when all points are on boundaries', () => {
    const points = [mkPoint(50, 50), mkPoint(50, 50), mkPoint(50, 50)];
    expect(computeRobustness(points)).toBe(0);
  });

  it('returns 50 when half points are fragile', () => {
    const points = [
      mkPoint(10, 10), mkPoint(10, 10), mkPoint(10, 10), mkPoint(10, 10), mkPoint(10, 10),
      mkPoint(50, 50), mkPoint(50, 50), mkPoint(50, 50), mkPoint(50, 50), mkPoint(50, 50),
    ];
    expect(computeRobustness(points)).toBe(50);
  });

  it('treats x-near-boundary as fragile even if y is far', () => {
    const points = [mkPoint(50, 80)];
    expect(computeRobustness(points)).toBe(0);
  });

  it('uses strict < at threshold boundary', () => {
    // 距边界恰好 = EDGE_THRESHOLD: 不算脆弱 (开区间)
    const pSafe = mkPoint(50 + EDGE_THRESHOLD, 80);
    expect(computeRobustness([pSafe])).toBe(100);
    // 距边界 < EDGE_THRESHOLD: 算脆弱
    const pFragile = mkPoint(50 + EDGE_THRESHOLD - 0.01, 80);
    expect(computeRobustness([pFragile])).toBe(0);
  });

  it('returns 0 for empty array', () => {
    expect(computeRobustness([])).toBe(0);
  });

  it('exports EDGE_THRESHOLD = 10', () => {
    expect(EDGE_THRESHOLD).toBe(10);
  });
});

import { gradeCoverage, gradeRobustness } from '../rotationHealth';

describe('gradeCoverage', () => {
  it('returns insufficient when n < 2', () => {
    expect(gradeCoverage(50, 0)).toBe('insufficient');
    expect(gradeCoverage(50, 1)).toBe('insufficient');
  });

  it('returns healthy when score >= 80', () => {
    expect(gradeCoverage(80, 10)).toBe('healthy');
    expect(gradeCoverage(95, 10)).toBe('healthy');
  });

  it('returns caution when 74 <= score < 80', () => {
    expect(gradeCoverage(74, 10)).toBe('caution');
    expect(gradeCoverage(79.9, 10)).toBe('caution');
  });

  it('returns imbalanced when score < 74', () => {
    expect(gradeCoverage(73.9, 10)).toBe('imbalanced');
    expect(gradeCoverage(0, 10)).toBe('imbalanced');
  });
});

describe('gradeRobustness', () => {
  it('returns insufficient when n < 1', () => {
    expect(gradeRobustness(50, 0)).toBe('insufficient');
  });

  it('returns healthy when score >= 77', () => {
    expect(gradeRobustness(77, 10)).toBe('healthy');
    expect(gradeRobustness(100, 10)).toBe('healthy');
  });

  it('returns caution when 69 <= score < 77', () => {
    expect(gradeRobustness(69, 10)).toBe('caution');
    expect(gradeRobustness(76.9, 10)).toBe('caution');
  });

  it('returns imbalanced when score < 69', () => {
    expect(gradeRobustness(68.9, 10)).toBe('imbalanced');
    expect(gradeRobustness(0, 10)).toBe('imbalanced');
  });
});

import { computeRotationHealth } from '../rotationHealth';
import type { Theme } from '@/types/themes';

const mkTheme = (id: string, longStr: number, shortStr: number): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: ['SOXX'],
  primary_us: 'SOXX',
  primary_cn: null,
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short: shortStr, mid: 50, long: longStr, composite: 50 },
  us_strength: { short: shortStr, mid: 50, long: longStr, composite: 50 },
  cn_strength: null,
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

describe('computeRotationHealth', () => {
  it('returns complete structure with both metrics', () => {
    const themes: Theme[] = [
      mkTheme('a', 80, 80), mkTheme('b', 80, 80), mkTheme('c', 80, 80),
      mkTheme('d', 20, 80), mkTheme('e', 20, 80), mkTheme('f', 20, 80),
      mkTheme('g', 20, 20), mkTheme('h', 20, 20), mkTheme('i', 20, 20),
      mkTheme('j', 80, 20), mkTheme('k', 80, 20), mkTheme('l', 80, 20),
    ];
    const h = computeRotationHealth(themes);
    expect(h.coverage.score).toBeCloseTo(100, 0);
    expect(h.coverage.grade).toBe('healthy');
    expect(h.robustness.score).toBe(100);
    expect(h.robustness.grade).toBe('healthy');
  });

  it('handles empty themes array', () => {
    const h = computeRotationHealth([]);
    expect(h.coverage.score).toBe(0);
    expect(h.coverage.grade).toBe('insufficient');
    expect(h.robustness.score).toBe(0);
    expect(h.robustness.grade).toBe('insufficient');
  });

  it('handles single-theme array (coverage insufficient, robustness computed)', () => {
    const h = computeRotationHealth([mkTheme('a', 10, 10)]);
    expect(h.coverage.grade).toBe('insufficient');
    expect(h.robustness.score).toBe(100); // (10,10) 远离边界
    expect(h.robustness.grade).toBe('healthy');
  });

  it('rounds scores to integers in returned structure', () => {
    const themes: Theme[] = [
      mkTheme('a', 80, 80), mkTheme('b', 80, 80), mkTheme('c', 80, 80),
      mkTheme('d', 20, 20), mkTheme('e', 20, 20), mkTheme('f', 20, 20),
    ];
    const h = computeRotationHealth(themes);
    expect(Number.isInteger(h.coverage.score)).toBe(true);
    expect(Number.isInteger(h.robustness.score)).toBe(true);
  });
});
