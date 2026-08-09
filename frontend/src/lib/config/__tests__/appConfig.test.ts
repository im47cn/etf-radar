import { describe, it, expect } from 'vitest';
import { appConfig } from '../appConfig';

describe('appConfig', () => {
  it('freeHoldingsLimit 默认值为 5（env 未设置时回落）', () => {
    // env 在测试环境默认未注入 → 走 fallback
    expect(appConfig.freeHoldingsLimit).toBe(5);
  });

  it('freeHoldingsLimit 是正整数', () => {
    expect(Number.isInteger(appConfig.freeHoldingsLimit)).toBe(true);
    expect(appConfig.freeHoldingsLimit).toBeGreaterThan(0);
  });

  it('appConfig 是只读常量（as const 锁定形状）', () => {
    expect(Object.keys(appConfig)).toEqual(['freeHoldingsLimit']);
  });
});
