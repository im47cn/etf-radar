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
          tags: ['DRAM'],
          note: '',
          returns: {
            r_1d: 0.01, r_5d: 0.05, r_20d: null, r_60d: null,
            r_120d: null, r_ytd: null,
          },
          strength: { short: 77, mid: 99, long: 99, composite: 95 },
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
  it('parses valid meta', () => {
    const valid = {
      schema_version: '1.0',
      last_full_refresh: { us: '2026-06-10T06:30:00+08:00', cn: null },
      last_intraday_refresh: null,
      providers: {
        us: { status: 'ok' as const, name: 'yfinance' },
        cn: { status: 'degraded' as const, name: 'akshare' },
      },
      failed_symbols: ['512720'],
      stale_minutes: 0,
      calendar: {
        us_trading_today: true, cn_trading_today: true,
        us_session_active: false, cn_session_active: true,
      },
    };
    const parsed = MetaFileSchema.parse(valid);
    expect(parsed.providers.cn.status).toBe('degraded');
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
