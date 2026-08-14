import { z } from 'zod';

// 可空数值统一 null (项目规则: .nullish().transform 兼容历史缺省)
const num = () => z.number().nullish().transform((v) => v ?? null);

/** IC 按 horizon 聚合 (1d/5d/20d): 均值 + 全样本 min-max + 最近实际. */
export const IcHorizonSchema = z.object({
  horizon: z.number(),
  ic: num(),
  t_stat: num(),
  n: num(),
  ic_min: num(),
  ic_max: num(),
  recent_ic: num(),
});
export type IcHorizon = z.infer<typeof IcHorizonSchema>;

/** 多窗口滚动 IC 时序点 (5/20/60 日窗口, forward 20d 收益). */
export const IcRollingSchema = z.object({
  date: z.string(),
  ic_5: num(),
  ic_20: num(),
  ic_60: num(),
});
export type IcRolling = z.infer<typeof IcRollingSchema>;

/** 主题 ARCH 检验 (r² Ljung-Box) + 收益白噪. */
export const ArchThemeSchema = z.object({
  theme_id: z.string(),
  name: z.string().optional(),
  n: num(),
  r2_lb_p: num(),
  is_arch: z.boolean().nullish().transform((v) => v ?? null),
  ret_lb_p: num(),
});
export type ArchTheme = z.infer<typeof ArchThemeSchema>;

/** 主题网格适配度复合分 (波动率 + Hurst 均值回归 + ARCH 持续, percentile rank 加权). */
export const GridFitnessThemeSchema = z.object({
  theme_id: z.string(),
  name: z.string().optional(),
  n: num(),
  ann_vol: num(),
  hurst: num(),
  arch_neg_log10p: num(),
  // 趋势护栏: 近 60/120 日累计收益 + regime 判定 ('down'/'up'/null=震荡)
  ret_60d: num(),
  ret_120d: num(),
  trend_regime: z.string().nullish().transform((v) => v ?? null),
  pct_vol: num(),
  pct_mean_reversion: num(),
  pct_arch: num(),
  grid_score: num(),
  verdict: z.string().nullish().transform((v) => v ?? null),
});
export type GridFitnessTheme = z.infer<typeof GridFitnessThemeSchema>;

/** data/latest/signal_evidence.json 契约 (schema 1.0): 5 年样本外统计证据. */
export const SignalEvidenceSchema = z
  .object({
    schema_version: z.string(),
    generated_at: z.string().optional(),
    as_of_date: z.string().optional(),
    sample: z
      .object({
        start: z.string().optional(),
        end: z.string().optional(),
        n_days: num(),
      })
      .passthrough(),
    ic: z
      .object({
        rolling: z.array(IcRollingSchema),
        by_horizon: z.array(IcHorizonSchema),
      })
      .passthrough(),
    arch: z
      .object({
        themes: z.array(ArchThemeSchema),
        summary: z
          .object({
            arch_count: num(),
            tested: num(),
            expected_fp: num(),
          })
          .passthrough(),
        // theme_id -> r² ACF(0..15); lag0 恒为 1.0
        representative_acf: z.record(z.string(), z.array(num())),
        // ARCH 显著比例滚动时序 (120 日窗口按月步进, n≈120 功效充足)
        time_series: z.array(
          z.object({
            period: z.string(),
            arch_ratio: num(),
            arch_count: num(),
            tested: num(),
          }),
        ),
      })
      .passthrough(),
    // 网格适配度复合分 (波动率0.40 + 均值回归0.35 + ARCH0.25); verdict: suitable/marginal/unsuitable
    grid_fitness: z
      .object({
        themes: z.array(GridFitnessThemeSchema).default([]),
        summary: z
          .object({
            tested: num(),
            skipped: num(),
            suitable_count: num(),
            median_score: num(),
          })
          .passthrough(),
        weights: z
          .object({
            vol: num(),
            mean_reversion: num(),
            arch: num(),
          })
          .passthrough(),
      })
      .nullish()
      .transform((v) => v ?? null),
  })
  .passthrough();
export type SignalEvidence = z.infer<typeof SignalEvidenceSchema>;
