import type { Theme } from '@/types/themes';
import type { SnapshotsIndex, SnapshotFrame } from '@/types/snapshots';

export const mkTheme = (
  id: string,
  long = 50,
  short = 50,
  composite = 50,
): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: ['X'],
  primary_us: 'X',
  primary_cn: null,
  tags: [],
  note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short, mid: 50, long, composite },
  us_strength: null,
  cn_strength: null,
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

export const mkThemes = (n = 14): Theme[] =>
  Array.from({ length: n }, (_, i) =>
    mkTheme(`t${i}`, 10 + i * 5, 10 + i * 5, 10 + i * 5),
  );

/**
 * cn_only 主题工厂: primary_us=null + primary_cn 指定 + cn-only tag,
 * 用于覆盖 A 股本土赛道的过滤分支 (Task 13).
 */
export const mkCnOnlyTheme = (
  id = 'cn_baijiu',
  cn_etf = '512690',
  name = '白酒',
): Theme => ({
  id,
  name,
  us_etfs: [],
  primary_us: null,
  primary_cn: cn_etf,
  tags: ['cn-only', 'consumer'],
  note: 'A 股本土赛道',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short: 55, mid: 60, long: 50, composite: 55 },
  us_strength: null,
  cn_strength: { short: 55, mid: 60, long: 50, composite: 55 },
  rank: { short: 5, mid: 5, long: 5, composite: 5 },
});

export const mkIndex = (n = 5): SnapshotsIndex => {
  const snapshots = Array.from({ length: n }, (_, i) => {
    const date = new Date(Date.UTC(2026, 0, 2 + i)).toISOString().slice(0, 10);
    return { date, themes_path: `snapshots/${date}/themes.json` };
  });
  return {
    schema_version: '1.0',
    generated_at: '2026-06-15T00:00:00+08:00',
    snapshots,
  };
};

export const mkFrame = (date: string, n = 14): SnapshotFrame => ({
  date,
  themes: mkThemes(n),
});
