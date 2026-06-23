// frontend/src/lib/portfolio/__tests__/eventDiff.test.ts

import { describe, it, expect } from 'vitest';
import { detectEvents } from '../eventDiff';
import { today, yesterday } from './__fixtures__/snapshots-pair';
import type { Snapshot } from '../eventTypes';

const holdings = (themeIds: string[]) =>
  themeIds.map(id => ({ themeId: id, etfCode: `${id}-etf` }));

describe('detectEvents', () => {
  it('同象限同强度同信号 — 无事件', () => {
    const events = detectEvents(today, yesterday, holdings(['cn_tech']));
    expect(events).toHaveLength(0);
  });

  it('象限切换产生 theme_quadrant_change 事件', () => {
    const events = detectEvents(today, yesterday, holdings(['cn_chemical']));
    const quadrant = events.find(e => e.event_type === 'theme_quadrant_change');
    expect(quadrant).toBeDefined();
    expect(quadrant!.event_signature).toBe(
      'theme_quadrant_change:cn_chemical:2026-06-23:weak_to_leading',
    );
    expect(quadrant!.payload).toEqual({ from: 'weak', to: 'leading' });
  });

  it('上穿阈值产生 theme_strength_cross_up 事件（每档单独）', () => {
    const consumeEvents = detectEvents(today, yesterday, holdings(['cn_consume']));
    const upEvents = consumeEvents.filter(e => e.event_type === 'theme_strength_cross_up');
    expect(upEvents).toHaveLength(1);
    expect(upEvents[0].event_signature).toBe(
      'theme_strength_cross_up:cn_consume:2026-06-23:25',
    );
    expect(upEvents[0].payload).toEqual({ threshold: 25, from: 24, to: 26 });
  });

  it('下穿阈值产生 theme_strength_cross_down 事件（多档同时）', () => {
    const events = detectEvents(today, yesterday, holdings(['cn_energy']));
    const downEvents = events.filter(e => e.event_type === 'theme_strength_cross_down');
    expect(downEvents.map(e => e.payload.threshold).sort()).toEqual([50]);
  });

  it('信号变化产生 theme_signal_change 事件', () => {
    const events = detectEvents(today, yesterday, holdings(['cn_consume']));
    const sig = events.find(e => e.event_type === 'theme_signal_change');
    expect(sig).toBeDefined();
    expect(sig!.payload).toEqual({ from: 'divergence', to: 'resonance' });
    expect(sig!.event_signature).toBe(
      'theme_signal_change:cn_consume:2026-06-23:divergence_to_resonance',
    );
  });

  it('多 holdings 共享同主题只生成一组事件（按 themeId 去重）', () => {
    const events = detectEvents(
      today, yesterday,
      [{ themeId: 'cn_chemical', etfCode: '512480' },
       { themeId: 'cn_chemical', etfCode: '512560' }],
    );
    const sigs = new Set(events.map(e => e.event_signature));
    expect(sigs.size).toBe(events.length);
  });

  it('主题在 yesterday 缺失 — 跳过（新增主题不报错）', () => {
    const yWithout: Snapshot = { date: yesterday.date, themes: new Map() };
    const events = detectEvents(today, yWithout, holdings(['cn_tech']));
    expect(events).toEqual([]);
  });

  it('主题在 today 缺失 — 跳过（下架主题不报错）', () => {
    const tWithout: Snapshot = { date: today.date, themes: new Map() };
    const events = detectEvents(tWithout, yesterday, holdings(['cn_tech']));
    expect(events).toEqual([]);
  });

  it('精确边界：composite 24 → 25 上穿（含等于）', () => {
    const y: Snapshot = {
      date: '2026-06-22',
      themes: new Map([['x', { themeId: 'x', quadrant: 'weak',
        strength: { short: 24, mid: 24, long: 24, composite: 24 }, signal: 'resonance' }]]),
    };
    const t: Snapshot = {
      date: '2026-06-23',
      themes: new Map([['x', { themeId: 'x', quadrant: 'weak',
        strength: { short: 25, mid: 25, long: 25, composite: 25 }, signal: 'resonance' }]]),
    };
    const events = detectEvents(t, y, [{ themeId: 'x', etfCode: 'x-etf' }]);
    expect(events.filter(e => e.event_type === 'theme_strength_cross_up')).toHaveLength(1);
  });

  it('精确边界：composite 25 → 24 下穿', () => {
    const y: Snapshot = {
      date: '2026-06-22',
      themes: new Map([['x', { themeId: 'x', quadrant: 'weak',
        strength: { short: 25, mid: 25, long: 25, composite: 25 }, signal: 'resonance' }]]),
    };
    const t: Snapshot = {
      date: '2026-06-23',
      themes: new Map([['x', { themeId: 'x', quadrant: 'weak',
        strength: { short: 24, mid: 24, long: 24, composite: 24 }, signal: 'resonance' }]]),
    };
    const events = detectEvents(t, y, [{ themeId: 'x', etfCode: 'x-etf' }]);
    expect(events.filter(e => e.event_type === 'theme_strength_cross_down')).toHaveLength(1);
  });
});
