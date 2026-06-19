import { describe, it, expect } from 'vitest';
import { ThemesFileSchema } from '../themes';
import { EtfsFileSchema } from '../etfs';
import { SignalsFileSchema } from '../signals';
import { MetaFileSchema } from '../meta';

describe('ThemesFileSchema', () => {
  it('parses valid themes file', () => {
    const valid = {
      schema_version: '1.0',
      generated_at: '2026-06-10T01:00:00+08:00',
      themes: [
        {
          id: 'storage_dram',
          name: '存储芯片',
          us_etfs: ['DRAM', 'SOXX'],
          primary_us: 'DRAM',
          primary_cn: null,
          tags: ['DRAM'],
          note: '',
          returns: {
            r_1d: 0.01, r_5d: 0.05, r_20d: null, r_60d: null,
            r_120d: null, r_ytd: null,
          },
          strength: { short: 77, mid: 99, long: 99, composite: 95 },
          us_strength: null,
          cn_strength: null,
          rank: { short: 1, mid: 1, long: 1, composite: 1 },
        },
      ],
    };
    const parsed = ThemesFileSchema.parse(valid);
    expect(parsed.themes).toHaveLength(1);
    expect(parsed.themes[0].id).toBe('storage_dram');
  });

  it('rejects missing required field', () => {
    const invalid = {
      schema_version: '1.0',
      generated_at: '2026-06-10T01:00:00+08:00',
      themes: [
        {
          id: 'x',
          // missing 'name'
          us_etfs: [],
          primary_us: 'X',
          tags: [],
          note: '',
          returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
          strength: { short: 0, mid: 0, long: 0, composite: 0 },
          rank: { short: 0, mid: 0, long: 0, composite: 0 },
        },
      ],
    };
    expect(() => ThemesFileSchema.parse(invalid)).toThrow();
  });
});

describe('SignalsFileSchema', () => {
  it('rejects invalid SignalType', () => {
    const bad = {
      schema_version: '1.0',
      generated_at: '2026-06-10T01:00:00+08:00',
      summary: {
        themes_total: 14, etfs_total: 20,
        resonance_count: 0, transmission_count: 0, divergence_count: 0,
        top_theme: null,
      },
      theme_signals: [
        {
          theme_id: 'x',
          signal: 'bogus',  // not in enum
          trigger_cn_etf: null,
          votes: { short: null, mid: null, long: null },
          description: '',
        },
      ],
      pair_signals: [],
    };
    expect(() => SignalsFileSchema.parse(bad)).toThrow();
  });
});

describe('MetaFileSchema', () => {
  const baseMeta = {
    schema_version: '1.1',
    last_full_refresh: { us: '2026-06-10T06:30:00+08:00', cn: null },
    last_intraday_refresh: null,
    providers: {
      us: { status: 'ok' as const, name: 'yfinance' },
      cn: { status: 'degraded' as const, name: 'akshare-em' },
    },
    failed_symbols: ['512720'],
    stale_minutes: 0,
    calendar: {
      us_trading_today: true, cn_trading_today: true,
      us_session_active: false, cn_session_active: true,
    },
  };

  it('parses valid meta', () => {
    const parsed = MetaFileSchema.parse(baseMeta);
    expect(parsed.providers.cn.status).toBe('degraded');
  });

  it('accepts fallback status', () => {
    const meta = {
      ...baseMeta,
      providers: { ...baseMeta.providers, cn: { status: 'fallback' as const, name: 'akshare-em' } },
    };
    const parsed = MetaFileSchema.parse(meta);
    expect(parsed.providers.cn.status).toBe('fallback');
  });

  it('parses meta with fallback_symbols map', () => {
    const m = MetaFileSchema.parse({ ...baseMeta, fallback_symbols: { '159755': 'akshare-sina' } });
    expect(m.fallback_symbols).toEqual({ '159755': 'akshare-sina' });
  });

  it('defaults fallback_symbols to {} when missing', () => {
    const m = MetaFileSchema.parse(baseMeta);
    expect(m.fallback_symbols).toEqual({});
  });
});

describe('EtfsFileSchema', () => {
  it('accepts amount_yi null (yfinance side)', () => {
    const valid = {
      schema_version: '1.0',
      generated_at: '2026-06-10T01:00:00+08:00',
      etfs: [
        {
          code: '512480',
          name: '半导体ETF',
          tracking_index: '中证全指半导体',
          returns: { r_1d: 0.01, r_5d: 0.05, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
          amount_yi: null,
          price: 1.234,
          strength: { short: 50, mid: 50, long: 50, composite: 50 },
        },
      ],
    };
    const parsed = EtfsFileSchema.parse(valid);
    expect(parsed.etfs[0].amount_yi).toBeNull();
  });
});

// ----- 数值约束 (立场 B): 数值越界一律拒绝 -----

const validTheme = {
  id: 'x', name: 'X', us_etfs: ['A'], primary_us: 'A', primary_cn: null,
  tags: [], note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short: 0, mid: 0, long: 0, composite: 0 },
  us_strength: null,
  cn_strength: null,
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
};
const validThemesFile = {
  schema_version: '1.0', generated_at: '2026-06-10T00:00:00Z', themes: [validTheme],
};

describe('Strength constraints', () => {
  it('rejects negative score', () => {
    const bad = { ...validThemesFile, themes: [{ ...validTheme, strength: { ...validTheme.strength, short: -1 } }] };
    expect(() => ThemesFileSchema.parse(bad)).toThrow();
  });
  it('rejects score > 99 (上限 99, 留 100 给"完美样本")', () => {
    const bad = { ...validThemesFile, themes: [{ ...validTheme, strength: { ...validTheme.strength, short: 150 } }] };
    expect(() => ThemesFileSchema.parse(bad)).toThrow();
  });
  it('rejects non-integer score', () => {
    const bad = { ...validThemesFile, themes: [{ ...validTheme, strength: { ...validTheme.strength, short: 50.5 } }] };
    expect(() => ThemesFileSchema.parse(bad)).toThrow();
  });
  it('accepts boundary values 0 and 99', () => {
    const ok = { ...validThemesFile, themes: [{ ...validTheme, strength: { short: 0, mid: 99, long: 50, composite: 0 } }] };
    expect(() => ThemesFileSchema.parse(ok)).not.toThrow();
  });
});

describe('Rank constraints', () => {
  it('rejects rank 0 (must be ≥1)', () => {
    const bad = { ...validThemesFile, themes: [{ ...validTheme, rank: { short: 0, mid: 1, long: 1, composite: 1 } }] };
    expect(() => ThemesFileSchema.parse(bad)).toThrow();
  });
  it('rejects fractional rank', () => {
    const bad = { ...validThemesFile, themes: [{ ...validTheme, rank: { short: 1.5, mid: 1, long: 1, composite: 1 } }] };
    expect(() => ThemesFileSchema.parse(bad)).toThrow();
  });
});

describe('MetaFile constraints', () => {
  const validMeta = {
    schema_version: '1.0',
    last_full_refresh: { us: null, cn: null },
    last_intraday_refresh: null,
    providers: {
      us: { status: 'ok' as const, name: 'yfinance' },
      cn: { status: 'ok' as const, name: 'akshare' },
    },
    failed_symbols: [],
    stale_minutes: 0,
    calendar: { us_trading_today: true, cn_trading_today: true, us_session_active: false, cn_session_active: false },
  };
  it('rejects negative stale_minutes', () => {
    expect(() => MetaFileSchema.parse({ ...validMeta, stale_minutes: -10 })).toThrow();
  });
  it('rejects non-integer stale_minutes', () => {
    expect(() => MetaFileSchema.parse({ ...validMeta, stale_minutes: 5.5 })).toThrow();
  });
});

describe('Etf price/amount constraints', () => {
  const baseEtfFile = {
    schema_version: '1.0',
    generated_at: '2026-06-10T01:00:00+08:00',
    etfs: [{
      code: '512480',
      name: 'X',
      tracking_index: 'Y',
      returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
      amount_yi: 0,
      price: 1.234,
      strength: { short: 0, mid: 0, long: 0, composite: 0 },
    }],
  };
  it('rejects negative amount_yi', () => {
    const bad = { ...baseEtfFile, etfs: [{ ...baseEtfFile.etfs[0], amount_yi: -1.5 }] };
    expect(() => EtfsFileSchema.parse(bad)).toThrow();
  });
  it('rejects zero or negative price', () => {
    const bad = { ...baseEtfFile, etfs: [{ ...baseEtfFile.etfs[0], price: 0 }] };
    expect(() => EtfsFileSchema.parse(bad)).toThrow();
  });
});
