import { describe, it, expect } from 'vitest';
import { diagnoseStructure } from '../structureInsight';
import type { AggregatedStock } from '@/types/holdings';

function s(code: string, strength60: number | null): AggregatedStock {
  return {
    code, name: code, cumulativeWeight: 1, sourceEtfs: ['x'], spot: null,
    indicators: {
      name: code, strength_60d: strength60, strength_20d: null,
      rsi_14: null, vol_ratio: null, leader: '',
    },
  };
}

describe('diagnoseStructure', () => {
  it('head_led: 1-2 强股带动', () => {
    const stocks = [s('a', 90), s('b', 50), s('c', 45), s('d', 40), s('e', 35)];
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('head_led');
    expect(r.text).toContain('龙头带动');
  });

  it('broad_strength: ≥6 只 strength ≥ 70', () => {
    const stocks = ['a', 'b', 'c', 'd', 'e', 'f'].map(c => s(c, 75));
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('broad_strength');
    expect(r.text).toContain('全面走强');
  });

  it('divergent: 强度方差大无明显头部', () => {
    const stocks = [s('a', 85), s('b', 70), s('c', 60), s('d', 30), s('e', 20)];
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('divergent');
  });

  it('weak: 均值 < 50', () => {
    const stocks = ['a', 'b', 'c', 'd', 'e'].map(c => s(c, 40));
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('weak');
    expect(r.text).toContain('偏弱');
  });

  it('no_data: 全部 strength_60d 为 null', () => {
    const stocks = ['a', 'b'].map(c => s(c, null));
    const r = diagnoseStructure(stocks);
    expect(r.type).toBe('no_data');
  });
});
