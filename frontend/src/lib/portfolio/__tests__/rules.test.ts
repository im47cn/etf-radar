import { describe, it, expect } from 'vitest';
import { strengthTag, momentumTag, quadrantLabel, buildNarrative, computeQuadrant } from '../rules';
import type { HoldingScore, Strength } from '../types';

describe('strengthTag', () => {
  it.each([
    [0,   '偏弱'],
    [24,  '偏弱'],
    [25,  '中性偏弱'],
    [49,  '中性偏弱'],
    [50,  '中性偏强'],
    [74,  '中性偏强'],
    [75,  '偏强'],
    [100, '偏强'],
  ])('composite=%i → %s', (c, expected) => {
    expect(strengthTag(c)).toBe(expected);
  });
});

describe('momentumTag', () => {
  it('short>=70 && mid>=60 → 动量向上', () => {
    expect(momentumTag(70, 60)).toBe('动量向上');
    expect(momentumTag(85, 75)).toBe('动量向上');
  });
  it('short<=30 && mid<=40 → 动量向下', () => {
    expect(momentumTag(30, 40)).toBe('动量向下');
    expect(momentumTag(10, 20)).toBe('动量向下');
  });
  it('其他 → null', () => {
    expect(momentumTag(50, 50)).toBeNull();
    expect(momentumTag(70, 50)).toBeNull();
    expect(momentumTag(30, 50)).toBeNull();
  });
});

describe('computeQuadrant', () => {
  // X=long, Y=short, 中线 50
  it.each([
    [75, 75, 'leading'],
    [75, 25, 'weakening'],
    [25, 75, 'following'],
    [25, 25, 'weak'],
    [50, 50, 'leading'],   // 边界归 leading（>= 50）
  ])('long=%i short=%i → %s', (long, short, expected) => {
    expect(computeQuadrant({ short, mid: 0, long, composite: 0 } as Strength)).toBe(expected);
  });
});

describe('quadrantLabel', () => {
  it('returns Chinese labels', () => {
    expect(quadrantLabel('leading')).toBe('领涨象限');
    expect(quadrantLabel('weakening')).toBe('转弱象限');
    expect(quadrantLabel('following')).toBe('跟随象限');
    expect(quadrantLabel('weak')).toBe('弱势象限');
  });
});

describe('buildNarrative', () => {
  const base: Partial<HoldingScore> = {
    status: 'covered',
    quadrant: 'leading',
    selfStrength: { short: 90, mid: 80, long: 95, composite: 88 },
  };

  it('强势 + mid 强 + 共振', () => {
    const s = { ...base, themeSignal: 'resonance' } as HoldingScore;
    expect(buildNarrative(s)).toContain('位于领涨象限');
    expect(buildNarrative(s)).toContain('综合强度 88 分位');
    expect(buildNarrative(s)).toContain('中周期强劲');
    expect(buildNarrative(s)).toContain('美股 A 股共振');
  });

  it('弱势 + mid 弱 + 背离', () => {
    const s: HoldingScore = {
      etfCode: 'X',
      status:  'covered',
      shares:  1, costPrice: null, currentPrice: null, marketValue: null, pnlPct: null, pnlAbs: null,
      quadrant: 'weak',
      selfStrength: { short: 10, mid: 15, long: 12, composite: 13 },
      themeSignal:  'divergence',
    };
    const n = buildNarrative(s);
    expect(n).toContain('弱势象限');
    expect(n).toContain('中周期走弱');
    expect(n).toContain('美股 A 股背离');
  });

  it('中性 mid → 不输出中周期标签', () => {
    const s: HoldingScore = {
      etfCode: 'X', status: 'covered',
      shares: 1, costPrice: null, currentPrice: null, marketValue: null, pnlPct: null, pnlAbs: null,
      quadrant: 'leading',
      selfStrength: { short: 60, mid: 50, long: 60, composite: 57 },
    };
    expect(buildNarrative(s)).not.toContain('中周期');
  });

  it('绝不出现"建议/买入/卖出/加仓/减仓"', () => {
    const s: HoldingScore = {
      etfCode: 'X', status: 'covered',
      shares: 1, costPrice: null, currentPrice: null, marketValue: null, pnlPct: null, pnlAbs: null,
      quadrant: 'weak',
      selfStrength: { short: 10, mid: 10, long: 10, composite: 10 },
      themeSignal:  'divergence',
    };
    const n = buildNarrative(s);
    expect(n).not.toMatch(/建议|买入|卖出|加仓|减仓/);
  });
});
