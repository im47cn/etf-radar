import { describe, it, expect } from 'vitest';
import { classifyQuadrant, themesToRotationPoints, QUADRANT_COLORS } from '../rotation';
import type { Theme } from '@/types/themes';

const mkTheme = (id: string, long: number, short: number, composite: number): Theme => ({
  id,
  name: id,
  us_etfs: ['X'],
  primary_us: 'X',
  tags: [],
  note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short, mid: 50, long, composite },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

describe('classifyQuadrant', () => {
  it.each([
    [60, 60, 'leading'],
    [30, 60, 'rising'],
    [30, 30, 'lagging'],
    [60, 30, 'fading'],
    [50, 50, 'leading'],
    [49, 49, 'lagging'],
  ] as const)('long=%i short=%i → %s', (long, short, expected) => {
    expect(classifyQuadrant(long, short)).toBe(expected);
  });
});

describe('themesToRotationPoints', () => {
  it('maps strength fields correctly', () => {
    const points = themesToRotationPoints([mkTheme('t1', 75, 80, 95)]);
    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({
      themeId: 't1',
      themeName: 't1',
      x: 75,
      y: 80,
      size: 95,
      quadrant: 'leading',
    });
  });

  it('preserves theme order', () => {
    const points = themesToRotationPoints([
      mkTheme('a', 10, 10, 10),
      mkTheme('b', 90, 90, 90),
    ]);
    expect(points.map(p => p.themeId)).toEqual(['a', 'b']);
  });

  it('handles empty array', () => {
    expect(themesToRotationPoints([])).toEqual([]);
  });
});

describe('QUADRANT_COLORS', () => {
  it('exposes 4 quadrant colors', () => {
    expect(Object.keys(QUADRANT_COLORS).sort()).toEqual(['fading', 'lagging', 'leading', 'rising']);
  });
});
