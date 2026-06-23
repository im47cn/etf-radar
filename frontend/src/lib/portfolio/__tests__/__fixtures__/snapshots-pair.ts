// frontend/src/lib/portfolio/__tests__/__fixtures__/snapshots-pair.ts
// detectEvents 测试用快照对，覆盖全部 4 种事件类型

import type { Snapshot, ThemeSnapshotEntry } from '../../eventTypes';

const mk = (
  themeId:   string,
  quadrant:  ThemeSnapshotEntry['quadrant'],
  composite: number,
  signal:    ThemeSnapshotEntry['signal'] = 'resonance',
): ThemeSnapshotEntry => ({
  themeId,
  quadrant,
  strength: { short: composite, mid: composite, long: composite, composite },
  signal,
});

export const yesterday: Snapshot = {
  date: '2026-06-22',
  themes: new Map<string, ThemeSnapshotEntry>([
    ['cn_tech',     mk('cn_tech',     'leading',   80, 'resonance')],
    ['cn_consume',  mk('cn_consume',  'following', 24, 'divergence')],
    ['cn_chemical', mk('cn_chemical', 'weak',      49, 'transmission')],
    ['cn_energy',   mk('cn_energy',   'weakening', 70, 'resonance')],
  ]),
};

export const today: Snapshot = {
  date: '2026-06-23',
  themes: new Map<string, ThemeSnapshotEntry>([
    ['cn_tech',     mk('cn_tech',     'leading',   80, 'resonance')],
    ['cn_consume',  mk('cn_consume',  'following', 26, 'resonance')],
    ['cn_chemical', mk('cn_chemical', 'leading',   60, 'transmission')],
    ['cn_energy',   mk('cn_energy',   'weakening', 49, 'resonance')],
  ]),
};
