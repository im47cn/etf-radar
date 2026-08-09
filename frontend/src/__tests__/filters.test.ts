import { describe, expect, it } from 'vitest';
import { filterThemes } from '@/lib/filters';
import type { Theme } from '@/types/themes';
import type { ThemeSignal } from '@/types/signals';

const mkTheme = (id: string, name: string, extra: Partial<Theme> = {}): Theme => ({
  id,
  name,
  us_etfs: [],
  primary_us: null,
  primary_cn: null,
  tags: [],
  note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short: 50, mid: 50, long: 50, composite: 50 },
  us_strength: null,
  cn_strength: null,
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
  ...extra,
});

const mkSignal = (themeId: string, signal: 'resonance' | 'transmission' | 'divergence' | null): ThemeSignal => ({
  theme_id: themeId,
  signal,
  trigger_cn_etf: null,
  votes: { short: null, mid: null, long: null },
  description: '',
});

describe('filterThemes', () => {
  it('signalFilter=all 全量返回', () => {
    const themes = [mkTheme('a', 'A'), mkTheme('b', 'B')];
    const map = new Map();
    const r = filterThemes(themes, map, 'all', '');
    expect(r).toHaveLength(2);
  });

  it('按信号类型过滤：命中保留，未命中或缺失剔除', () => {
    const themes = [mkTheme('a', 'A'), mkTheme('b', 'B'), mkTheme('c', 'C')];
    const map = new Map<string, ThemeSignal>([
      ['a', mkSignal('a', 'resonance')],
      ['b', mkSignal('b', 'transmission')],
    ]);
    const r = filterThemes(themes, map, 'resonance', '');
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe('a');
  });

  it('signal=null 的 theme 被剔除', () => {
    const themes = [mkTheme('a', 'A')];
    const map = new Map<string, ThemeSignal>([['a', mkSignal('a', null)]]);
    const r = filterThemes(themes, map, 'resonance', '');
    expect(r).toHaveLength(0);
  });

  it('搜索匹配主题名（不区分大小写 + 前后空格）', () => {
    const themes = [mkTheme('a', '半导体'), mkTheme('b', '银行')];
    const map = new Map();
    const r = filterThemes(themes, map, 'all', '  半导体  ');
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe('a');
  });

  it('搜索匹配 primary_us', () => {
    const themes = [mkTheme('a', 'A', { primary_us: 'SMH' })];
    const r = filterThemes(themes, new Map(), 'all', 'smh');
    expect(r).toHaveLength(1);
  });

  it('搜索匹配 us_etfs / tags', () => {
    const themes = [
      mkTheme('a', 'A', { us_etfs: ['XLK'], tags: ['tech'] }),
      mkTheme('b', 'B', { us_etfs: ['XLF'], tags: ['finance'] }),
    ];
    expect(filterThemes(themes, new Map(), 'all', 'xlk')).toHaveLength(1);
    expect(filterThemes(themes, new Map(), 'all', 'finance')).toHaveLength(1);
  });

  it('信号 + 搜索联合过滤', () => {
    const themes = [mkTheme('a', '半导体'), mkTheme('b', '半导体银行')];
    const map = new Map<string, ThemeSignal>([
      ['a', mkSignal('a', 'resonance')],
      ['b', mkSignal('b', 'divergence')],
    ]);
    const r = filterThemes(themes, map, 'resonance', '半导体');
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe('a');
  });
});
