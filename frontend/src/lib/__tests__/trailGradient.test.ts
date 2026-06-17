import { describe, it, expect } from 'vitest';
import { trailOpacity, pickTopByComposite, buildTrails } from '../trailGradient';
import { mkTheme, mkFrame } from '@/__fixtures__/snapshots';

describe('trailOpacity', () => {
  it('returns 0.05 for oldest (i=0)', () => {
    expect(trailOpacity(0, 10)).toBeCloseTo(0.05, 2);
  });

  it('returns 0.4 for newest (i=total-1)', () => {
    expect(trailOpacity(9, 10)).toBeCloseTo(0.4, 2);
  });

  it('returns 0.4 when total=1 (single point edge case)', () => {
    expect(trailOpacity(0, 1)).toBeCloseTo(0.4, 2);
  });

  it('increases monotonically', () => {
    const vals = [0, 1, 2, 3, 4, 5].map(i => trailOpacity(i, 6));
    for (let i = 1; i < vals.length; i++) {
      expect(vals[i]).toBeGreaterThan(vals[i - 1]);
    }
  });
});

describe('pickTopByComposite', () => {
  it('picks N highest composite themes', () => {
    const themes = [
      mkTheme('a', 50, 50, 90),
      mkTheme('b', 50, 50, 30),
      mkTheme('c', 50, 50, 70),
      mkTheme('d', 50, 50, 10),
    ];
    const top = pickTopByComposite(themes, 2);
    expect(top.size).toBe(2);
    expect(top.has('a')).toBe(true);
    expect(top.has('c')).toBe(true);
  });

  it('returns empty Set when n=0', () => {
    expect(pickTopByComposite([mkTheme('a', 50, 50, 90)], 0).size).toBe(0);
  });
});

describe('buildTrails', () => {
  it('returns trails only for topN themes', () => {
    const frames = [mkFrame('2026-01-01', 3), mkFrame('2026-01-02', 3)];
    const trails = buildTrails(frames, new Set(['t0', 't1']));
    expect(trails.size).toBe(2);
    expect(trails.has('t0')).toBe(true);
    expect(trails.has('t2')).toBe(false);
  });

  it('preserves frame order and assigns gradient opacity', () => {
    const frames = [mkFrame('2026-01-01', 1), mkFrame('2026-01-02', 1)];
    const trails = buildTrails(frames, new Set(['t0']));
    const points = trails.get('t0')!;
    expect(points).toHaveLength(2);
    expect(points[0].date).toBe('2026-01-01');
    expect(points[1].date).toBe('2026-01-02');
    expect(points[1].opacity).toBeGreaterThan(points[0].opacity);
  });
});
