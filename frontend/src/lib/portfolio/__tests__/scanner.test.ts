import { describe, it, expect } from 'vitest';
import { scanOpportunities, COMPOSITE_MIN, SHORT_MIN } from '../scanner';
import type { ThemeMetric } from '../types';

const mkTheme = (
  id: string,
  composite: number,
  short: number,
  overrides: Partial<ThemeMetric> = {},
): ThemeMetric => ({
  id,
  name:       `主题${id}`,
  primary_cn: `${id}-cn`,
  strength: { short, mid: 60, long: 60, composite },
  ...overrides,
});

describe('scanOpportunities', () => {
  it('返回 composite≥75 且 short≥70 的主题', () => {
    const themes = [
      mkTheme('a', 80, 75),  // 通过
      mkTheme('b', 74, 90),  // composite 不够
      mkTheme('c', 90, 69),  // short 不够
      mkTheme('d', 90, 90),  // 通过
    ];
    const result = scanOpportunities(themes, new Set());
    expect(result.map(o => o.themeId).sort()).toEqual(['a', 'd']);
  });

  it('排除 ownedThemeIds 中的主题', () => {
    const themes = [
      mkTheme('a', 90, 90),
      mkTheme('b', 90, 90),
    ];
    const result = scanOpportunities(themes, new Set(['a']));
    expect(result.map(o => o.themeId)).toEqual(['b']);
  });

  it('按 composite 降序排序', () => {
    const themes = [
      mkTheme('a', 80, 80),
      mkTheme('b', 95, 80),
      mkTheme('c', 85, 80),
    ];
    const result = scanOpportunities(themes, new Set());
    expect(result.map(o => o.themeId)).toEqual(['b', 'c', 'a']);
  });

  it('截前 10 只', () => {
    const themes = Array.from({ length: 15 }, (_, i) =>
      mkTheme(`t${i}`, 90 - i, 80),  // 强度递减
    );
    const result = scanOpportunities(themes, new Set());
    expect(result).toHaveLength(10);
    expect(result[0].themeId).toBe('t0');
    expect(result[9].themeId).toBe('t9');
  });

  it('携带 l2Tag 和 momentumTag', () => {
    // mkTheme 默认 mid=60, long=60；仅 override mid=70 让 momentumTag 触发"动量向上"
    const themes = [mkTheme('a', 80, 80, {
      strength: { short: 80, mid: 70, long: 60, composite: 80 },
    })];
    const result = scanOpportunities(themes, new Set());
    expect(result[0].l2Tag).toBe('偏强');           // composite 80 → 偏强
    expect(result[0].momentumTag).toBe('动量向上'); // short 80 + mid 70 → 动量向上
  });

  it('空主题列表返回空数组', () => {
    expect(scanOpportunities([], new Set())).toEqual([]);
  });

  it('所有主题被排除时返回空数组', () => {
    const themes = [mkTheme('a', 90, 90)];
    expect(scanOpportunities(themes, new Set(['a']))).toEqual([]);
  });

  it('阈值边界：低于常量值不入选（行为驱动，不锚定具体数字）', () => {
    const themes = [
      mkTheme('low_composite', COMPOSITE_MIN - 1, SHORT_MIN),     // composite 差 1 不通过
      mkTheme('low_short',     COMPOSITE_MIN,     SHORT_MIN - 1), // short 差 1 不通过
      mkTheme('exact_edge',    COMPOSITE_MIN,     SHORT_MIN),     // 等于阈值通过（含等于）
    ];
    const result = scanOpportunities(themes, new Set());
    expect(result.map(o => o.themeId)).toEqual(['exact_edge']);
  });
});
