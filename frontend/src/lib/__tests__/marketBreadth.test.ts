import { describe, expect, test } from 'vitest';
import { computeMarketBreadth } from '../marketBreadth';

describe('computeMarketBreadth', () => {
  test('空输入返回零广度、中位为 null', () => {
    const b = computeMarketBreadth([]);
    expect(b).toEqual({
      total: 0,
      up: 0,
      down: 0,
      flat: 0,
      breadthPct: 0,
      medianR1d: null,
    });
  });

  test('全 null 视同无有效样本', () => {
    expect(computeMarketBreadth([null, null])).toEqual({
      total: 0,
      up: 0,
      down: 0,
      flat: 0,
      breadthPct: 0,
      medianR1d: null,
    });
  });

  test('混合样本: 涨跌平计数、上涨占比、剔除 null', () => {
    // 有效值 [0.02, -0.01, 0, 0.03] → 排序 [-0.01, 0, 0.02, 0.03], 中位=(0+0.02)/2
    const b = computeMarketBreadth([0.02, -0.01, 0, 0.03, null]);
    expect(b.total).toBe(4);
    expect(b.up).toBe(2);
    expect(b.down).toBe(1);
    expect(b.flat).toBe(1);
    expect(b.breadthPct).toBe(50);
    expect(b.medianR1d).toBeCloseTo(0.01, 10);
  });

  test('奇数样本取中间值', () => {
    const b = computeMarketBreadth([-0.03, 0.01, 0.02]);
    expect(b.medianR1d).toBeCloseTo(0.01, 10);
  });

  test('全涨 → 上涨占比 100', () => {
    const b = computeMarketBreadth([0.01, 0.02, 0.005]);
    expect(b.up).toBe(3);
    expect(b.breadthPct).toBe(100);
  });
});
