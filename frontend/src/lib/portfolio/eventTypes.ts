// frontend/src/lib/portfolio/eventTypes.ts
// 主题级事件类型定义 — 供 detectEvents / Supabase 落库 / UI 消费

import { z } from 'zod';
import type { Quadrant, SignalKind, Strength } from './types';

/** 一日的主题级快照视图（detectEvents 输入） */
export interface ThemeSnapshotEntry {
  themeId:  string;
  quadrant: Quadrant;
  strength: Strength;
  signal:   SignalKind | null;
}

export interface Snapshot {
  date:   string;                           // YYYY-MM-DD
  themes: Map<string, ThemeSnapshotEntry>;  // by themeId
}

export type EventType =
  | 'theme_quadrant_change'
  | 'theme_strength_cross_up'
  | 'theme_strength_cross_down'
  | 'theme_signal_change';

// ── Payload 形状定义 ──────────────────────────────────────────────────────────

/** 象限切换 payload */
export interface QuadrantChangePayload {
  from: Quadrant;
  to:   Quadrant;
}

/** 强度阈值穿越 payload（上穿 / 下穿共用） */
export interface StrengthCrossPayload {
  threshold: 25 | 50 | 75;
  from:      number;
  to:        number;
}

/** 信号变化 payload */
export interface SignalChangePayload {
  from: SignalKind;
  to:   SignalKind;
}

// ── 差分产出（尚未落库）—— discriminated union ────────────────────────────────

/** 差分产出（尚未落库） */
export type PendingEvent =
  | { event_type: 'theme_quadrant_change';     theme_id: string; event_signature: string; payload: QuadrantChangePayload; asof_date: string }
  | { event_type: 'theme_strength_cross_up';   theme_id: string; event_signature: string; payload: StrengthCrossPayload;  asof_date: string }
  | { event_type: 'theme_strength_cross_down'; theme_id: string; event_signature: string; payload: StrengthCrossPayload;  asof_date: string }
  | { event_type: 'theme_signal_change';       theme_id: string; event_signature: string; payload: SignalChangePayload;   asof_date: string };

// ── 从数据库读出 + 解析后的事件 —— discriminated union ────────────────────────

/** 从数据库读出 + 解析后的事件 */
export type UserEvent =
  | { id: string; user_id: string; event_type: 'theme_quadrant_change';     theme_id: string; event_signature: string; payload: QuadrantChangePayload; asof_date: string; created_at: string; read_at: string | null }
  | { id: string; user_id: string; event_type: 'theme_strength_cross_up';   theme_id: string; event_signature: string; payload: StrengthCrossPayload;  asof_date: string; created_at: string; read_at: string | null }
  | { id: string; user_id: string; event_type: 'theme_strength_cross_down'; theme_id: string; event_signature: string; payload: StrengthCrossPayload;  asof_date: string; created_at: string; read_at: string | null }
  | { id: string; user_id: string; event_type: 'theme_signal_change';       theme_id: string; event_signature: string; payload: SignalChangePayload;   asof_date: string; created_at: string; read_at: string | null };

// ── Zod 行级校验 schema — 与上方 UserEvent union 保持一致 ────────────────────

const QuadrantChangePayloadSchema = z.object({
  from: z.enum(['leading', 'weakening', 'following', 'weak']),
  to:   z.enum(['leading', 'weakening', 'following', 'weak']),
});
const StrengthCrossPayloadSchema = z.object({
  threshold: z.union([z.literal(25), z.literal(50), z.literal(75)]),
  from:      z.number(),
  to:        z.number(),
});
const SignalChangePayloadSchema = z.object({
  from: z.enum(['resonance', 'transmission', 'divergence']),
  to:   z.enum(['resonance', 'transmission', 'divergence']),
});

/** UserEvent 公共字段 */
const UserEventBase = z.object({
  id:              z.string(),
  user_id:         z.string(),
  theme_id:        z.string(),
  event_signature: z.string(),
  asof_date:       z.string(),
  created_at:      z.string(),
  read_at:         z.string().nullable(),
});

/** UserEvent 行级 zod schema — discriminated union 按 event_type 分发 */
export const UserEventSchema = z.discriminatedUnion('event_type', [
  UserEventBase.extend({ event_type: z.literal('theme_quadrant_change'),     payload: QuadrantChangePayloadSchema }),
  UserEventBase.extend({ event_type: z.literal('theme_strength_cross_up'),   payload: StrengthCrossPayloadSchema }),
  UserEventBase.extend({ event_type: z.literal('theme_strength_cross_down'), payload: StrengthCrossPayloadSchema }),
  UserEventBase.extend({ event_type: z.literal('theme_signal_change'),       payload: SignalChangePayloadSchema }),
]);
