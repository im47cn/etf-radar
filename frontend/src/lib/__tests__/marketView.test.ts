import { describe, it, expect } from 'vitest';
import {
  isCnOnly,
  pickStrength,
  themeMatchesView,
  marketViewToRotationMode,
} from '@/lib/marketView';
import type { Theme } from '@/types/themes';

const mkStrength = (n: number) => ({ short: n, mid: n, long: n, composite: n });

const mapped: Theme = {
  id: 'ai', name: 'AI', us_etfs: ['BOTZ'],
  primary_us: 'BOTZ', primary_cn: '159819',
  tags: [], note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: mkStrength(50),
  us_strength: mkStrength(60),
  cn_strength: mkStrength(40),
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
};

const cnOnly: Theme = {
  ...mapped, id: 'cn_liquor', name: '白酒',
  us_etfs: [], primary_us: null, primary_cn: '512690',
  us_strength: null,
  cn_strength: mkStrength(70),
};

describe('isCnOnly', () => {
  it('mapped theme returns false', () => expect(isCnOnly(mapped)).toBe(false));
  it('cn-only theme returns true', () => expect(isCnOnly(cnOnly)).toBe(true));
});

describe('pickStrength', () => {
  it('us view picks us_strength', () =>
    expect(pickStrength(mapped, 'us')).toEqual(mkStrength(60)));
  it('cn-all view picks cn_strength', () =>
    expect(pickStrength(mapped, 'cn-all')).toEqual(mkStrength(40)));
  it('cn-only view picks cn_strength', () =>
    expect(pickStrength(cnOnly, 'cn-only')).toEqual(mkStrength(70)));
  it('us view on cn-only returns null', () =>
    expect(pickStrength(cnOnly, 'us')).toBeNull());
});

describe('themeMatchesView', () => {
  it('us hides cn-only', () => {
    expect(themeMatchesView(mapped, 'us')).toBe(true);
    expect(themeMatchesView(cnOnly, 'us')).toBe(false);
  });
  it('cn-all keeps both', () => {
    expect(themeMatchesView(mapped, 'cn-all')).toBe(true);
    expect(themeMatchesView(cnOnly, 'cn-all')).toBe(true);
  });
  it('cn-only keeps only cn-only', () => {
    expect(themeMatchesView(mapped, 'cn-only')).toBe(false);
    expect(themeMatchesView(cnOnly, 'cn-only')).toBe(true);
  });
});

describe('marketViewToRotationMode', () => {
  it('us → us', () => expect(marketViewToRotationMode('us')).toBe('us'));
  it('cn-all → cn', () => expect(marketViewToRotationMode('cn-all')).toBe('cn'));
  it('cn-only → cn', () => expect(marketViewToRotationMode('cn-only')).toBe('cn'));
});
