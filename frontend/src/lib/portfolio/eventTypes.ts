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
//
// 命名约定：snake_case 与 DB jsonb 字段（asof_date / event_signature 等）保持一致。
//
// 字段语义：
//   - `version`：payload schema 版本号；未来 schema 变更时升 2/3，配合 zod
//      discriminatedUnion('version', ...) 支持历史行兼容渲染。
//   - `etf_codes`：事件**触发瞬间**用户持仓的 ETF 代码快照。
//      UNIQUE (user_id, event_signature) + ignoreDuplicates=true 决定了同主题/同日/
//      同跃迁只插一行，**后续持仓变化不会回写已落库事件**——事件是历史记录，不应被
//      篡改。UI 若想显示「当前仍持有的 ETF」，应用 etf_codes ∩ current_holdings
//      实时计算（见 eventDisplay.ts.formatAffectedEtfs）。

/** payload schema 当前版本号 */
export const PAYLOAD_VERSION = 1 as const;
export type PayloadVersion = typeof PAYLOAD_VERSION;

/** 象限切换 payload */
export interface QuadrantChangePayload {
  version:   PayloadVersion;
  from:      Quadrant;
  to:        Quadrant;
  etf_codes: string[];
}

/** 强度阈值穿越 payload（上穿 / 下穿共用） */
export interface StrengthCrossPayload {
  version:   PayloadVersion;
  threshold: 25 | 50 | 75;
  from:      number;
  to:        number;
  etf_codes: string[];
}

/** 信号变化 payload */
export interface SignalChangePayload {
  version:   PayloadVersion;
  from:      SignalKind;
  to:        SignalKind;
  etf_codes: string[];
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

const EtfCodesSchema = z.array(z.string());

// version 用 default(1) 兼容历史 jsonb 行（早期落库无 version 字段视为 v1）;
// 未来出 v2 时，本 schema 升级为 literal(1)，旧行通过升级器迁移或在 zod
// discriminatedUnion('version', [v1, v2, ...]) 分流处理.
const VersionSchema = z.literal(PAYLOAD_VERSION).optional().default(PAYLOAD_VERSION);

const QuadrantChangePayloadSchema = z.object({
  version:   VersionSchema,
  from:      z.enum(['leading', 'weakening', 'following', 'weak']),
  to:        z.enum(['leading', 'weakening', 'following', 'weak']),
  etf_codes: EtfCodesSchema,
});
const StrengthCrossPayloadSchema = z.object({
  version:   VersionSchema,
  threshold: z.union([z.literal(25), z.literal(50), z.literal(75)]),
  from:      z.number(),
  to:        z.number(),
  etf_codes: EtfCodesSchema,
});
const SignalChangePayloadSchema = z.object({
  version:   VersionSchema,
  from:      z.enum(['resonance', 'transmission', 'divergence']),
  to:        z.enum(['resonance', 'transmission', 'divergence']),
  etf_codes: EtfCodesSchema,
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
