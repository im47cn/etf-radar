import { describe, it, expect } from 'vitest';
import { formatPct, formatYi, formatStrength, formatRelativeTime } from '../format';

describe('formatPct', () => {
  it('formats positive as +X.X%', () => {
    expect(formatPct(0.123)).toBe('+12.3%');
  });
  it('formats negative as -X.X%', () => {
    expect(formatPct(-0.05)).toBe('-5.0%');
  });
  it('returns dash for null', () => {
    expect(formatPct(null)).toBe('—');
  });
  it('returns dash for undefined', () => {
    expect(formatPct(undefined)).toBe('—');
  });
  it('treats 0 as zero (no + sign)', () => {
    expect(formatPct(0)).toBe('0.0%');
  });
});

describe('formatYi', () => {
  it('formats with 亿 suffix', () => {
    expect(formatYi(1.234)).toBe('1.2亿');
  });
  it('null becomes dash', () => {
    expect(formatYi(null)).toBe('—');
  });
});

describe('formatStrength', () => {
  it('rounds integer strength', () => {
    expect(formatStrength(77)).toBe('77');
  });
  it('rounds .5 (banker rounding)', () => {
    expect(formatStrength(77.4)).toBe('77');
    expect(formatStrength(77.6)).toBe('78');
  });
});

describe('formatRelativeTime', () => {
  it('formats recent as "刚刚"', () => {
    const now = new Date('2026-06-10T10:00:00Z');
    expect(formatRelativeTime(now.toISOString(), now)).toBe('刚刚');
  });
  it('returns minutes ago', () => {
    const now = new Date('2026-06-10T10:00:00Z');
    const tenMinAgo = new Date('2026-06-10T09:50:00Z');
    expect(formatRelativeTime(tenMinAgo.toISOString(), now)).toBe('10分钟前');
  });
  it('returns hours ago', () => {
    const now = new Date('2026-06-10T10:00:00Z');
    const threeHrAgo = new Date('2026-06-10T07:00:00Z');
    expect(formatRelativeTime(threeHrAgo.toISOString(), now)).toBe('3小时前');
  });
});
