// frontend/src/lib/portfolio/eventDiff.ts
// 主题级事件差分 — 纯函数，无副作用，不依赖网络/DB

import { PAYLOAD_VERSION, type Snapshot, type PendingEvent } from './eventTypes';

/** spec §3.7 — composite 强度三档分界 */
const THRESHOLDS = [25, 50, 75] as const;

export interface HoldingForDiff {
  themeId: string;
  /** 持仓 ETF 代码 — 事件 payload 携带，用于 UI 回链「事件影响了你持仓的 SOXX / SMH」 */
  etfCode: string;
}

/**
 * 主题级事件差分。
 *
 * 立场：仅记录"信号事实变化"，不评判好坏。颜色/语义判断由 UI 层根据
 *   event_type + payload 推导（参见 EventItem.tsx）。
 *
 * 去重策略：同一主题被多个 ETF 持有时，按 themeId 聚合，事件仅生成一组
 *   （由 event_signature 中的 themeId 保证唯一）；payload.etf_codes
 *   收集该主题下用户持仓的全部 ETF 代码（保持输入顺序，去重）。
 */
export function detectEvents(
  today:     Snapshot,
  yesterday: Snapshot,
  holdings:  HoldingForDiff[],
): PendingEvent[] {
  // 先按 themeId 聚合 etfCodes（保持输入顺序去重）
  const themeToEtfs = new Map<string, string[]>();
  for (const h of holdings) {
    const list = themeToEtfs.get(h.themeId);
    if (list) {
      if (!list.includes(h.etfCode)) list.push(h.etfCode);
    } else {
      themeToEtfs.set(h.themeId, [h.etfCode]);
    }
  }

  const events: PendingEvent[] = [];
  for (const [themeId, etfCodes] of themeToEtfs) {
    const t = today.themes.get(themeId);
    const y = yesterday.themes.get(themeId);
    // 新增或下架主题：静默跳过，不产生事件
    if (!t || !y) continue;

    // 1. 象限切换
    if (t.quadrant !== y.quadrant) {
      events.push({
        event_type:      'theme_quadrant_change',
        theme_id:        themeId,
        event_signature: `theme_quadrant_change:${themeId}:${today.date}:${y.quadrant}_to_${t.quadrant}`,
        payload:         { version: PAYLOAD_VERSION, from: y.quadrant, to: t.quadrant, etf_codes: etfCodes },
        asof_date:       today.date,
      });
    }

    // 2. 强度阈值穿越（每档独立判断）
    const yComp = y.strength.composite;
    const tComp = t.strength.composite;
    for (const threshold of THRESHOLDS) {
      if (yComp < threshold && tComp >= threshold) {
        events.push({
          event_type:      'theme_strength_cross_up',
          theme_id:        themeId,
          event_signature: `theme_strength_cross_up:${themeId}:${today.date}:${threshold}`,
          payload:         { version: PAYLOAD_VERSION, threshold, from: yComp, to: tComp, etf_codes: etfCodes },
          asof_date:       today.date,
        });
      }
      if (yComp >= threshold && tComp < threshold) {
        events.push({
          event_type:      'theme_strength_cross_down',
          theme_id:        themeId,
          event_signature: `theme_strength_cross_down:${themeId}:${today.date}:${threshold}`,
          payload:         { version: PAYLOAD_VERSION, threshold, from: yComp, to: tComp, etf_codes: etfCodes },
          asof_date:       today.date,
        });
      }
    }

    // 3. 信号变化（null 视为无信号，不产生事件）
    if (t.signal !== y.signal && t.signal !== null && y.signal !== null) {
      events.push({
        event_type:      'theme_signal_change',
        theme_id:        themeId,
        event_signature: `theme_signal_change:${themeId}:${today.date}:${y.signal}_to_${t.signal}`,
        payload:         { version: PAYLOAD_VERSION, from: y.signal, to: t.signal, etf_codes: etfCodes },
        asof_date:       today.date,
      });
    }
  }

  return events;
}
