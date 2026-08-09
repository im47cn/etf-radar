import { describe, expect, it } from 'vitest';
import { formatPct, formatYi, formatStrength, formatRelativeTime } from '@/lib/format';

describe('formatPct', () => {
  it('null/undefined → 占位', () => {
    expect(formatPct(null)).toBe('—');
    expect(formatPct(undefined)).toBe('—');
  });

  it('正值带 + 号', () => {
    expect(formatPct(0.0123)).toBe('+1.2%');
  });

  it('负值无 + 号', () => {
    expect(formatPct(-0.005)).toBe('-0.5%');
  });

  it('零无 + 号', () => {
    expect(formatPct(0)).toBe('0.0%');
  });
});

describe('formatYi', () => {
  it('null/undefined → 占位', () => {
    expect(formatYi(null)).toBe('—');
    expect(formatYi(undefined)).toBe('—');
  });

  it('数值格式化', () => {
    expect(formatYi(12.34)).toBe('12.3亿');
  });
});

describe('formatStrength', () => {
  it('null/undefined → 占位', () => {
    expect(formatStrength(null)).toBe('—');
    expect(formatStrength(undefined)).toBe('—');
  });

  it('四舍五入', () => {
    expect(formatStrength(49.6)).toBe('50');
    expect(formatStrength(49.4)).toBe('49');
  });
});

describe('formatRelativeTime', () => {
  const now = new Date('2026-08-09T12:00:00Z');

  it('空值 → 占位', () => {
    expect(formatRelativeTime(null, now)).toBe('—');
    expect(formatRelativeTime(undefined, now)).toBe('—');
    expect(formatRelativeTime('', now)).toBe('—');
  });

  it('< 1 分钟 → 刚刚', () => {
    expect(formatRelativeTime('2026-08-09T11:59:30Z', now)).toBe('刚刚');
  });

  it('< 60 分钟 → N分钟前', () => {
    expect(formatRelativeTime('2026-08-09T11:30:00Z', now)).toBe('30分钟前');
  });

  it('< 24 小时 → N小时前', () => {
    expect(formatRelativeTime('2026-08-09T06:00:00Z', now)).toBe('6小时前');
  });

  it('>= 24 小时 → 月-日 时:分', () => {
    // now 在 UTC 12:00, 本地时区取决于环境, 但跨越 24h 一定走最后分支
    const old = new Date(now.getTime() - 30 * 60 * 60000).toISOString(); // 30h ago
    const r = formatRelativeTime(old, now);
    expect(r).toMatch(/\d+-\d+ \d{2}:\d{2}/);
  });
});
