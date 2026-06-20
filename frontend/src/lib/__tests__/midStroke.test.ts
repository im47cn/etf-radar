import { describe, it, expect } from 'vitest';
import {
  computeMidTertiles,
  midToStrokeWidth,
  STROKE_WIDTH_LOW,
  STROKE_WIDTH_MID,
  STROKE_WIDTH_HIGH,
} from '../midStroke';

describe('computeMidTertiles', () => {
  it('空数组返回 0 默认', () => {
    expect(computeMidTertiles([])).toEqual({ q33: 0, q67: 0 });
  });

  it('单值数组 q33=q67=该值', () => {
    expect(computeMidTertiles([42])).toEqual({ q33: 42, q67: 42 });
  });

  it('全相同值,分位 = 该值', () => {
    expect(computeMidTertiles([50, 50, 50, 50, 50])).toEqual({ q33: 50, q67: 50 });
  });

  it('三值 [30, 50, 70]: 索引法 q33=index1=50, q67=index2=70', () => {
    expect(computeMidTertiles([30, 50, 70])).toEqual({ q33: 50, q67: 70 });
  });

  it('打乱输入不影响结果 (内部排序)', () => {
    const a = computeMidTertiles([70, 30, 50, 60, 40, 80, 20, 90, 10]);
    const b = computeMidTertiles([10, 20, 30, 40, 50, 60, 70, 80, 90]);
    expect(a).toEqual(b);
  });

  it('9 值: idx33=3, idx67=6 → q33=40, q67=70', () => {
    expect(computeMidTertiles([10, 20, 30, 40, 50, 60, 70, 80, 90])).toEqual({
      q33: 40,
      q67: 70,
    });
  });
});

describe('midToStrokeWidth', () => {
  const t = { q33: 40, q67: 70 };

  it('mid < q33 → LOW', () => {
    expect(midToStrokeWidth(20, t)).toBe(STROKE_WIDTH_LOW);
    expect(midToStrokeWidth(39, t)).toBe(STROKE_WIDTH_LOW);
  });

  it('q33 ≤ mid < q67 → MID (边界 q33 走 MID)', () => {
    expect(midToStrokeWidth(40, t)).toBe(STROKE_WIDTH_MID);
    expect(midToStrokeWidth(55, t)).toBe(STROKE_WIDTH_MID);
    expect(midToStrokeWidth(69, t)).toBe(STROKE_WIDTH_MID);
  });

  it('mid ≥ q67 → HIGH (边界 q67 走 HIGH)', () => {
    expect(midToStrokeWidth(70, t)).toBe(STROKE_WIDTH_HIGH);
    expect(midToStrokeWidth(99, t)).toBe(STROKE_WIDTH_HIGH);
  });

  it('全相同分位 (q33=q67=50): 50 走 HIGH,49 走 LOW', () => {
    const flat = { q33: 50, q67: 50 };
    expect(midToStrokeWidth(50, flat)).toBe(STROKE_WIDTH_HIGH);
    expect(midToStrokeWidth(49, flat)).toBe(STROKE_WIDTH_LOW);
  });

  it('档值常量: LOW < MID < HIGH 且都 > 0', () => {
    expect(STROKE_WIDTH_LOW).toBeGreaterThan(0);
    expect(STROKE_WIDTH_LOW).toBeLessThan(STROKE_WIDTH_MID);
    expect(STROKE_WIDTH_MID).toBeLessThan(STROKE_WIDTH_HIGH);
  });
});
