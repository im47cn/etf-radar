// frontend/src/lib/trading/types.ts
// 交易数据层类型（对应 Supabase 006_trades.sql 三表）+ zod 行校验
// 模式仿 lib/watchlist/types.ts：DB 行 zod safeParse，坏行静默过滤

import { z } from 'zod';

// ========== trades：交易事件流 ==========
export const TradeSideSchema = z.enum(['open', 'add', 'reduce', 'close']);
export type TradeSide = z.infer<typeof TradeSideSchema>;

export const TradeSchema = z.object({
  id:         z.string().uuid(),
  user_id:    z.string().uuid(),
  code:       z.string().regex(/^\d{6}$/, '必须是 6 位数字代码'),
  name:       z.string(),
  side:       TradeSideSchema,
  trade_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, '日期格式 YYYY-MM-DD'),
  price:      z.number().positive(),
  shares:     z.number().int().positive(),
  stop_after: z.number().positive().nullable(),
  reason:     z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Trade = z.infer<typeof TradeSchema>;

// 写入输入（id/user_id/时间戳由服务端生成）
export interface TradeInput {
  code:       string;
  name:       string;
  side:       TradeSide;
  trade_date: string;
  price:      number;
  shares:     number;
  stop_after?: number | null;
  reason?:    string | null;
}

// ========== trade_reviews：复盘评分（Actions 写，本人只读） ==========
export const TradeReviewSchema = z.object({
  id:              z.string().uuid(),
  user_id:         z.string().uuid(),
  trade_id:        z.string().uuid(),
  review_date:     z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  discipline_score: z.number().int().min(0).max(100).nullable(),
  result_r:        z.number().nullable(),
  mae_pct:         z.number().nullable(),
  events:          z.record(z.string(), z.unknown()).nullable(),
  computed_at:     z.string(),
});
export type TradeReview = z.infer<typeof TradeReviewSchema>;

// ========== trading_settings：交易参数（本人单行） ==========
export const TradingSettingsSchema = z.object({
  user_id:                z.string().uuid(),
  equity_cny:             z.number().positive().nullable(),
  risk_per_trade_pct:     z.number().positive(),
  max_positions:          z.number().int().positive(),
  max_position_pct:       z.number().positive(),
  max_portfolio_risk_pct: z.number().positive(),
  updated_at:             z.string(),
});
export type TradingSettings = z.infer<typeof TradingSettingsSchema>;

// 未建行 / 未配置时的默认值（规格 §1 第 7 条：0.75% 单笔风险、5 只、20% 单票、4% 组合）
export const DEFAULT_SETTINGS_VALUES = {
  equity_cny:             null as number | null,
  risk_per_trade_pct:     0.75,
  max_positions:          5,
  max_position_pct:       20,
  max_portfolio_risk_pct: 4,
} as const;

export type SettingsInput = Partial<{
  equity_cny:             number | null;
  risk_per_trade_pct:     number;
  max_positions:          number;
  max_position_pct:       number;
  max_portfolio_risk_pct: number;
}>;

// ========== 持仓（事件流推导产物，非 DB 表） ==========
export interface Position {
  code:         string;
  name:         string;
  shares:       number;          // 剩余股数（int）
  avg_cost:     number;          // 加权平均成本
  stop_current: number | null;   // 当前止损位（最近一笔携带的 stop_after）
}

// ========== 错误类型化 ==========
export type TradingApiErrorKind = 'not_configured' | 'unauthenticated' | 'db';

export class TradingApiError extends Error {
  readonly kind: TradingApiErrorKind;
  constructor(kind: TradingApiErrorKind, message: string) {
    super(message);
    this.name = 'TradingApiError';
    this.kind = kind;
  }
}
