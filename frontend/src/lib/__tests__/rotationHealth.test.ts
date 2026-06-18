import { describe, it, expect } from 'vitest';
import type { RotationPoint } from '@/types/rotation';
import { computeCoverage } from '../rotationHealth';

const mkPoint = (x: number, y: number, id = 't'): RotationPoint => ({
  themeId: id,
  themeName: id,
  x,
  y,
  size: 50,
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
