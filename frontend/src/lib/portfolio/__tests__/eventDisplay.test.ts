// frontend/src/lib/portfolio/__tests__/eventDisplay.test.ts

import { describe, it, expect } from 'vitest';
import { formatAffectedEtfs } from '../eventDisplay';
import type { UserEvent } from '../eventTypes';

const mkEvent = (etfCodes: string[]): UserEvent => ({
  id:              'e1',
  user_id:         'u1',
  event_type:      'theme_quadrant_change',
  theme_id:        't1',
  event_signature: 'sig1',
  payload:         { version: 1, from: 'weak', to: 'leading', etf_codes: etfCodes },
  asof_date:       '2026-06-23',
  created_at:      '2026-06-23T00:00:00Z',
  read_at:         null,
});

describe('formatAffectedEtfs', () => {
  it('触发时持有 + 现仍持有 → 「影响你持仓的 ...」', () => {
    const ev = mkEvent(['SOXX', 'SMH']);
    expect(formatAffectedEtfs(ev, new Set(['SOXX', 'SMH']))).toBe(
      '影响你持仓的 SOXX, SMH',
    );
  });

  it('部分仍持有 → 只列出仍持有的', () => {
    const ev = mkEvent(['SOXX', 'SMH']);
    expect(formatAffectedEtfs(ev, new Set(['SOXX']))).toBe(
      '影响你持仓的 SOXX',
    );
  });

  it('触发时持有 + 现已全部卖出 → 「曾涉及...（已卖出）」', () => {
    const ev = mkEvent(['SOXX']);
    expect(formatAffectedEtfs(ev, new Set(['QQQ']))).toBe(
      '曾涉及你持仓的 SOXX（已卖出）',
    );
  });

  it('etf_codes 为空 → null（降级由 UI 决定）', () => {
    const ev = mkEvent([]);
    expect(formatAffectedEtfs(ev, new Set(['SOXX']))).toBeNull();
  });

  it('currentHoldings 为空 → 显示已卖出', () => {
    const ev = mkEvent(['SOXX']);
    expect(formatAffectedEtfs(ev, new Set())).toBe(
      '曾涉及你持仓的 SOXX（已卖出）',
    );
  });
});
