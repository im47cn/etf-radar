import { describe, it, expect } from 'vitest';
import { trailOpacity, buildTrails } from '../trailGradient';
import { mkFrame } from '@/__fixtures__/snapshots';
import type { SnapshotFrame } from '@/types/snapshots';
import type { Theme } from '@/types/themes';

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

describe('buildTrails (adapted — old signature)', () => {
  it('returns trails only for specified themeIds', () => {
    const frames = [mkFrame('2026-01-01', 3), mkFrame('2026-01-02', 3)];
    const trails = buildTrails(frames, 'us', { themeIds: new Set(['t0', 't1']) });
    expect(trails.size).toBe(2);
    expect(trails.has('t0')).toBe(true);
    expect(trails.has('t2')).toBe(false);
  });

  it('preserves frame order and assigns gradient opacity', () => {
    const frames = [mkFrame('2026-01-01', 1), mkFrame('2026-01-02', 1)];
    const trails = buildTrails(frames, 'us', { themeIds: new Set(['t0']) });
    const points = trails.get('t0')!;
    expect(points).toHaveLength(2);
    expect(points[0].date).toBe('2026-01-01');
    expect(points[1].date).toBe('2026-01-02');
    expect(points[1].opacity).toBeGreaterThan(points[0].opacity);
  });
});

const mkTheme2 = (id: string, long: number, short: number, composite = 50): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: [],
  primary_us: '',
  primary_cn: null,
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short, mid: 50, long, composite },
  us_strength: { short, mid: 50, long, composite },
  cn_strength: null,
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

const mkFrame2 = (date: string, themes: Theme[]): SnapshotFrame => ({ date, themes });

describe('buildTrails (new signature)', () => {
  it('returns ALL themes when opts.themeIds is undefined', () => {
    const frames = [
      mkFrame2('2026-01-01', [mkTheme2('ai', 60, 70), mkTheme2('semi', 40, 30)]),
      mkFrame2('2026-01-02', [mkTheme2('ai', 65, 72), mkTheme2('semi', 45, 35)]),
    ];
    const trails = buildTrails(frames, 'us');
    expect(Array.from(trails.keys()).sort()).toEqual(['ai', 'semi']);
    expect(trails.get('ai')).toHaveLength(2);
    expect(trails.get('semi')).toHaveLength(2);
  });

  it('filters by opts.themeIds when provided', () => {
    const frames = [
      mkFrame2('2026-01-01', [mkTheme2('ai', 60, 70), mkTheme2('semi', 40, 30)]),
    ];
    const trails = buildTrails(frames, 'us', { themeIds: new Set(['ai']) });
    expect(Array.from(trails.keys())).toEqual(['ai']);
  });

  it('skips frames where theme is missing (mid-introduction)', () => {
    const frames = [
      mkFrame2('2026-01-01', [mkTheme2('ai', 60, 70)]),
      mkFrame2('2026-01-02', [mkTheme2('ai', 65, 72), mkTheme2('semi', 40, 30)]),
    ];
    const trails = buildTrails(frames, 'us');
    expect(trails.get('ai')).toHaveLength(2);
    expect(trails.get('semi')).toHaveLength(1);
    expect(trails.get('semi')?.[0].date).toBe('2026-01-02');
  });

  it('opacity ascends from oldest to newest', () => {
    const frames = [
      mkFrame2('2026-01-01', [mkTheme2('ai', 60, 70)]),
      mkFrame2('2026-01-02', [mkTheme2('ai', 65, 72)]),
      mkFrame2('2026-01-03', [mkTheme2('ai', 70, 75)]),
    ];
    const trails = buildTrails(frames, 'us');
    const pts = trails.get('ai')!;
    expect(pts[0].opacity).toBeLessThan(pts[2].opacity);
  });

  it('returns empty map when frames are empty', () => {
    const trails = buildTrails([], 'us');
    expect(trails.size).toBe(0);
  });
});

// ---- Step 4.1: mode-aware tests ----

const mkS = (long: number, short: number) => ({
  short, mid: 0, long, composite: 0,
});

const mapped = (long: number, short: number): Theme => ({
  id: 'ai',
  name: 'AI',
  us_etfs: [],
  primary_us: 'BOTZ',
  primary_cn: '159819',
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: mkS(long, short),
  us_strength: mkS(long + 10, short + 10),
  cn_strength: mkS(long - 10, short - 10),
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

const f = (date: string, themes: Theme[]): SnapshotFrame => ({ date, themes });

describe('buildTrails mode-aware', () => {
  it('mode=us 取 us_strength 坐标', () => {
    const frames = [f('d1', [mapped(50, 50)])];
    const m = buildTrails(frames, 'us');
    expect(m.get('ai')?.[0]).toMatchObject({ x: 60, y: 60 });
  });

  it('mode=cn 取 cn_strength 坐标', () => {
    const frames = [f('d1', [mapped(50, 50)])];
    const m = buildTrails(frames, 'cn');
    expect(m.get('ai')?.[0]).toMatchObject({ x: 40, y: 40 });
  });

  it('us_strength=null (旧 schema 1.0 frame) 回退到 strength', () => {
    const legacy: Theme = { ...mapped(50, 50), us_strength: null, cn_strength: null };
    const frames = [f('d1', [legacy])];
    const m = buildTrails(frames, 'us');
    expect(m.get('ai')?.[0]).toMatchObject({ x: 50, y: 50 });
  });

  it('cn-only 主题在 mode=us 时跳过', () => {
    const cnOnly: Theme = {
      ...mapped(50, 50), primary_us: null, us_strength: null,
      cn_strength: mkS(70, 70),
    };
    const frames = [f('d1', [cnOnly])];
    const m = buildTrails(frames, 'us');
    expect(m.get('ai')).toBeUndefined();
  });

  it('us-only 主题在 mode=cn 时跳过 (对称镜像)', () => {
    const usOnly: Theme = {
      ...mapped(50, 50), primary_cn: null,
      us_strength: mkS(70, 70), cn_strength: null,
    };
    const frames = [f('d1', [usOnly])];
    const m = buildTrails(frames, 'cn');
    expect(m.get('ai')).toBeUndefined();
  });

  it('多帧部分跳过: 3 帧含 1 帧 cn-only, mode=us → trail 长度=2', () => {
    const cnOnlyFrame: Theme = {
      ...mapped(50, 50), primary_us: null, us_strength: null,
      cn_strength: mkS(70, 70),
    };
    const frames = [
      f('d1', [mapped(50, 50)]),     // us_strength 有值 → 计入
      f('d2', [cnOnlyFrame]),         // us_strength=null & cn_strength!=null → 跳过
      f('d3', [mapped(55, 55)]),     // us_strength 有值 → 计入
    ];
    const m = buildTrails(frames, 'us');
    const pts = m.get('ai');
    expect(pts).toHaveLength(2);
    expect(pts?.map(p => p.date)).toEqual(['d1', 'd3']);
  });
});
