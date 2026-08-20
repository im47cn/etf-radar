import { z } from 'zod';

// 与 backend tests/schemas/trading.schema.json (SEPA spec §2.3) 对齐; 所有数值字段
// 允许 null (数据降级), nullish → null 兼容缺省产物 (schema 演进约定, 同 metals).
const num = z.number().nullish().transform((v) => v ?? null);
const str = z.string().nullish().transform((v) => v ?? null);
const bool = z.boolean().nullish().transform((v) => v ?? null);

/** 环境档位: offense=进攻 / neutral=中性 / defense=防守. */
export const TradingRegimeSchema = z.enum(['offense', 'neutral', 'defense']);
export type TradingRegime = z.infer<typeof TradingRegimeSchema>;

/** 候选状态机 (事实语义, spec §0 合规立场: 禁指令词汇). */
export const TradingCandidateStateSchema = z.enum(['in_buy_zone', 'near_buy_zone', 'watch']);
export type TradingCandidateState = z.infer<typeof TradingCandidateStateSchema>;

/** 指数趋势模板结果: template_pass x/8 + 8 条布尔 criteria. */
export const TradingIndexSchema = z.object({
  code: z.string(),
  name: str,
  template_pass: num,
  criteria: z.array(z.boolean()).default([]),
  close: num,
});
export type TradingIndex = z.infer<typeof TradingIndexSchema>;

/** 宽度佐证 (market_temperature.json, 只展示不进档位公式). 值为小数占比. */
export const TradingBreadthSchema = z.object({
  ma20_pct: num,
  ma60_pct: num,
  ma120_pct: num,
  source: str,
});
export type TradingBreadth = z.infer<typeof TradingBreadthSchema>;

export const TradingEnvironmentSchema = z.object({
  regime: TradingRegimeSchema.nullish().transform((v) => v ?? null),
  indices: z.array(TradingIndexSchema).default([]),
  breadth: TradingBreadthSchema.nullish().transform((v) => v ?? null),
  source_status: z.record(z.string(), str).default({}),
});
export type TradingEnvironment = z.infer<typeof TradingEnvironmentSchema>;

/** VCP 形态识别结果: 收缩次数 / 基部深度% / 质量分 0-1 / 末端量能萎缩. */
export const TradingVcpSchema = z.object({
  contractions: num,
  depth_pct: num,
  quality: num,
  volume_dryup: bool,
});
export type TradingVcp = z.infer<typeof TradingVcpSchema>;

/** 候选个股 (≤50, 按 composite_score 降序). */
export const TradingCandidateSchema = z.object({
  code: z.string(),
  name: str,
  composite_score: num,
  stage: num,
  template_pass: num,
  rs_pct: num,
  vcp: TradingVcpSchema.nullish().transform((v) => v ?? null),
  pivot: num,
  buy_zone_low: num,
  buy_zone_high: num,
  stop: num,
  state: TradingCandidateStateSchema.nullish().transform((v) => v ?? null),
  limit_up_unexecutable: bool,
  chg_pct: num,
  board: str,
  vol_forecast_ann: num,
});
export type TradingCandidate = z.infer<typeof TradingCandidateSchema>;

/** 筛选漏斗各级存量. */
export const TradingUniverseStatsSchema = z.object({
  total: num,
  tradable: num,
  stage2: num,
  vcp: num,
  top: num,
});
export type TradingUniverseStats = z.infer<typeof TradingUniverseStatsSchema>;

export const TradingSchema = z
  .object({
    schema_version: z.string(),
    generated_at: z.string(),
    environment: TradingEnvironmentSchema.nullish().transform((v) => v ?? null),
    candidates: z.array(TradingCandidateSchema).default([]),
    universe_stats: TradingUniverseStatsSchema.nullish().transform((v) => v ?? null),
  })
  .passthrough();
export type Trading = z.infer<typeof TradingSchema>;
