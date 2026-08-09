import { describe, it, expect } from 'vitest';
import {
  STRENGTH_TIERS,
  strengthTier,
  RSI_ZONES,
  rsiColor,
  VOL_RATIO_THRESHOLDS,
  volRatioColor,
} from '../indicatorThresholds';

describe('strengthTier', () => {
  it('≥90 极强', () => {
    expect(strengthTier(90).label).toBe('极强');
    expect(strengthTier(100).label).toBe('极强');
  });
  it('80-89 强', () => {
    expect(strengthTier(80).label).toBe('强');
    expect(strengthTier(89).label).toBe('强');
  });
  it('60-79 中性', () => {
    expect(strengthTier(60).label).toBe('中性');
    expect(strengthTier(79).label).toBe('中性');
  });
  it('40-59 偏弱', () => {
    expect(strengthTier(40).label).toBe('偏弱');
    expect(strengthTier(59).label).toBe('偏弱');
  });
  it('0-39 弱', () => {
    expect(strengthTier(0).label).toBe('弱');
    expect(strengthTier(39).label).toBe('弱');
  });
  it('STRENGTH_TIERS 有 5 档', () => {
    expect(STRENGTH_TIERS).toHaveLength(5);
  });
});

describe('rsiColor', () => {
  it('≥70 overbought → red', () => {
    expect(rsiColor(70)).toContain('red');
    expect(rsiColor(80)).toContain('red');
  });
  it('50-69 bullish zone → orange', () => {
    expect(rsiColor(50)).toContain('orange');
    expect(rsiColor(69)).toContain('orange');
  });
  it('≤30 oversold → blue', () => {
    expect(rsiColor(30)).toContain('blue');
    expect(rsiColor(20)).toContain('blue');
  });
  it('31-49 neutral → gray', () => {
    expect(rsiColor(31)).toContain('gray');
    expect(rsiColor(49)).toContain('gray');
  });
  it('RSI_ZONES 常量正确', () => {
    expect(RSI_ZONES.overbought).toBe(70);
    expect(RSI_ZONES.oversold).toBe(30);
  });
});

describe('volRatioColor', () => {
  it('≥2.0 high → red', () => {
    expect(volRatioColor(2.0)).toContain('red');
    expect(volRatioColor(3.0)).toContain('red');
  });
  it('≤0.5 low → blue', () => {
    expect(volRatioColor(0.5)).toContain('blue');
    expect(volRatioColor(0.1)).toContain('blue');
  });
  it('0.51-1.99 normal → gray', () => {
    expect(volRatioColor(1.0)).toContain('gray');
    expect(volRatioColor(0.51)).toContain('gray');
  });
  it('VOL_RATIO_THRESHOLDS 常量正确', () => {
    expect(VOL_RATIO_THRESHOLDS.high).toBe(2.0);
    expect(VOL_RATIO_THRESHOLDS.low).toBe(0.5);
  });
});
