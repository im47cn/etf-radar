import { describe, expect, it } from 'vitest';
import { tagColor } from '@/lib/portfolio/tagColor';

describe('tagColor', () => {
  it('偏强 → green', () => {
    expect(tagColor('偏强')).toBe('bg-green-100 text-green-700');
  });

  it('中性偏强 → light green', () => {
    expect(tagColor('中性偏强')).toBe('bg-green-50 text-green-600');
  });

  it('中性偏弱 → orange', () => {
    expect(tagColor('中性偏弱')).toBe('bg-orange-50 text-orange-600');
  });

  it('偏弱 → red', () => {
    expect(tagColor('偏弱')).toBe('bg-red-100 text-red-700');
  });

  it('动量向上 → blue', () => {
    expect(tagColor('动量向上')).toBe('bg-blue-100 text-blue-700');
  });

  it('动量向下 → amber', () => {
    expect(tagColor('动量向下')).toBe('bg-amber-100 text-amber-700');
  });

  it('未知/undefined → gray', () => {
    expect(tagColor('未知')).toBe('bg-gray-100 text-gray-600');
    expect(tagColor(undefined)).toBe('bg-gray-100 text-gray-600');
  });
});
