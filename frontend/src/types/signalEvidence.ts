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
      })
      .passthrough(),
  })
  .passthrough();
export type SignalEvidence = z.infer<typeof SignalEvidenceSchema>;
