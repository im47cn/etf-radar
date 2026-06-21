// frontend/src/lib/portfolio/types.ts

import { z } from 'zod';

// ========== 持仓（Supabase 表对应） ==========
export const HoldingSchema = z.object({
  id:          z.string().uuid(),
  user_id:     z.string().uuid(),
  etf_code:    z.string().regex(/^\d{6}$/, '必须是 6 位数字代码'),
  shares:      z.number().positive(),
  cost_price:  z.number().positive().nullable(),
  note:        z.string().nullable(),
  created_at:  z.string(),
  updated_at:  z.string(),
});
export type Holding = z.infer<typeof HoldingSchema>;

// ========== 信号融合产物 ==========
export interface Strength {
  short:     number;
  mid:       number;
  long:      number;
  composite: number;
}

export type StrengthTag = '偏强' | '中性偏强' | '中性偏弱' | '偏弱';
export type MomentumTag = '动量向上' | '动量向下';
export type Quadrant    = 'leading' | 'weakening' | 'following' | 'weak';
export type SignalKind  = 'resonance' | 'transmission' | 'divergence';

export interface HoldingScore {
  etfCode: string;
  status:  'covered' | 'uncovered';

  // 基础信息（两种都有）
  name?:        string;
  shares:       number;
  costPrice:    number | null;
  currentPrice: number | null;
  marketValue:  number | null;
  pnlPct:       number | null;
  pnlAbs:       number | null;

  // 仅 covered
  selfStrength?:    Strength;
  themeId?:         string;
  themeName?:       string;
  themeUsStrength?: Strength;
  themeCnStrength?: Strength;
  themeSignal?:     SignalKind;
  quadrant?:        Quadrant;
  l2Tag?:           StrengthTag;
  momentumTag?:     MomentumTag | null;
  narrative?:       string;
}

// ========== 引擎输入（轻量重定义，避免依赖 zod schemas） ==========
export interface ThemeMetric {
  id:           string;
  name:         string;
  primary_cn:   string;
  strength:     Strength;
  us_strength?: Strength;
  cn_strength?: Strength;
}

export interface EtfMetric {
  code:          string;
  name:          string;
  tracking_index?: string;
  price:         number;
  strength:      Strength;
}

export interface ThemeSignalEntry {
  theme_id: string;
  signal:   SignalKind;
}

export interface ScoreInputs {
  holdings:     Holding[];
  themes:       ThemeMetric[];
  etfs:         EtfMetric[];
  themeSignals: ThemeSignalEntry[];
}
