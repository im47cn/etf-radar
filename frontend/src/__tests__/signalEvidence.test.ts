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
    };
    const d = SignalEvidenceSchema.parse(raw);
    expect(d.sample.n_days).toBe(1212);
    expect(d.ic.by_horizon[0].ic).toBeCloseTo(0.054);
    expect(d.arch.themes[0].is_arch).toBe(true);
    expect(d.arch.representative_acf.semiconductor[0]).toBe(1.0);
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
