import { describe, it, expect } from 'vitest';
import { asOfLabel } from '../AsOfBadge';

describe('asOfLabel', () => {
  it('数据为今日时返回 null(UpdateBadge 已够)', () => {
    expect(asOfLabel('2026-07-08', '2026-07-08')).toBeNull();
  });

  it('数据非今日时返回 "数据截至 MM-DD"', () => {
    expect(asOfLabel('2026-07-06', '2026-07-08')).toBe('数据截至 07-06');
  });

  it('缺 cn_data_date 时返回 null', () => {
    expect(asOfLabel(null, '2026-07-08')).toBeNull();
    expect(asOfLabel(undefined, '2026-07-08')).toBeNull();
  });
});
