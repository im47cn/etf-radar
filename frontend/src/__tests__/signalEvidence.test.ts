import { describe, expect, it } from 'vitest';
import { SignalEvidenceSchema } from '@/types/signalEvidence';

describe('SignalEvidenceSchema', () => {
  const minimal = {
    schema_version: '1.0',
    sample: {},
    ic: { rolling: [], by_horizon: [] },
    arch: { themes: [], summary: {}, representative_acf: {}, time_series: [] },
  };

  it('解析完整证据对象并保留数值', () => {
    const raw = {
      ...minimal,
      as_of_date: '2026-08-07',
      sample: { start: '2021-08-09', end: '2026-08-07', n_days: 1212 },
      ic: {
        rolling: [{ date: '2021-11-09', ic: 0.03, n: 60 }],
        by_horizon: [{ horizon: 20, ic: 0.054, t_stat: 7.9, n: 1192 }],
      },
      arch: {
        themes: [{ theme_id: 'semiconductor', name: '半导体', n: 1212, r2_lb_p: 0.0, is_arch: true, ret_lb_p: 0.02 }],
        summary: { arch_count: 26, tested: 30, expected_fp: 1.5 },
        representative_acf: { semiconductor: [1.0, 0.18] },
        time_series: [
          { period: '2024-09', arch_ratio: 0.55, arch_count: 16, tested: 29 },
          { period: '2024-10', arch_ratio: 0.66, arch_count: 19, tested: 29 },
        ],
      },
      grid_fitness: {
        themes: [{ theme_id: 'semi', name: '半导体', n: 1212, ann_vol: 0.32, hurst: 0.42,
                  arch_neg_log10p: 5, pct_vol: 0.9, pct_mean_reversion: 0.7, pct_arch: 0.9,
                  grid_score: 0.82, verdict: 'suitable',
                  ret_60d: -0.02, ret_120d: 0.05, trend_regime: null }],
        summary: { tested: 29, skipped: 1, suitable_count: 12, median_score: 0.52 },
        weights: { vol: 0.4, mean_reversion: 0.35, arch: 0.25 },
      },
    };
    const d = SignalEvidenceSchema.parse(raw);
    expect(d.sample.n_days).toBe(1212);
    expect(d.ic.by_horizon[0].ic).toBeCloseTo(0.054);
    expect(d.arch.themes[0].is_arch).toBe(true);
    expect(d.arch.representative_acf.semiconductor[0]).toBe(1.0);
    expect(d.grid_fitness?.themes[0].verdict).toBe('suitable');
    expect(d.grid_fitness?.themes[0].trend_regime).toBeNull();
    expect(d.grid_fitness?.themes[0].ret_120d).toBe(0.05);
    expect(d.grid_fitness?.summary.suitable_count).toBe(12);
  });

  it('历史 snapshot 缺 ret/trend 字段 → null (趋势护栏向后兼容)', () => {
    const legacy = {
      ...minimal,
      grid_fitness: {
        themes: [{ theme_id: 'semi', grid_score: 0.82, verdict: 'suitable' }],
        summary: { tested: 29, skipped: 1, suitable_count: 12, median_score: 0.52 },
        weights: { vol: 0.4, mean_reversion: 0.35, arch: 0.25 },
      },
    };
    const t = SignalEvidenceSchema.parse(legacy).grid_fitness?.themes[0];
    expect(t?.ret_60d).toBeNull();
    expect(t?.ret_120d).toBeNull();
    expect(t?.trend_regime).toBeNull();
  });

  it('缺省数值统一为 null (项目 .nullish().transform 规则)', () => {
    const d = SignalEvidenceSchema.parse(minimal);
    expect(d.sample.n_days).toBeNull();
    expect(d.ic.by_horizon).toEqual([]);
  });

  it('passthrough 兼容历史/未知字段', () => {
    const d = SignalEvidenceSchema.parse({ ...minimal, extra: 'x', sample: { unk: 1 } });
    expect((d as Record<string, unknown>).extra).toBe('x');
  });
});
