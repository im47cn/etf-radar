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
