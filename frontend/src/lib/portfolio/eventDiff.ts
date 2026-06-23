// frontend/src/lib/portfolio/eventDiff.ts
// 主题级事件差分 — 纯函数，无副作用，不依赖网络/DB

import type { Snapshot, PendingEvent } from './eventTypes';

/** spec §3.7 — composite 强度三档分界 */
const THRESHOLDS = [25, 50, 75] as const;

export interface HoldingForDiff {
  themeId: string;
  /** 持仓 ETF 代码 — 可选，仅用于上层日志/告警回链；事件聚合仍按 themeId 去重 */
  etfCode?: string;
}

/**
 * 主题级事件差分。
 *
 * 立场：仅记录"信号事实变化"，不评判好坏。颜色/语义判断由 UI 层根据
 *   event_type + payload 推导（参见 EventItem.tsx）。
 *
 * 去重策略：同一主题被多个 ETF 持有时，按 themeId 聚合，事件仅生成一组
 *   （由 event_signature 中的 themeId 保证唯一）。
 */
export function detectEvents(
  today:     Snapshot,
  yesterday: Snapshot,
  holdings:  HoldingForDiff[],
): PendingEvent[] {
  const events: PendingEvent[] = [];
  const seenThemes = new Set<string>();

  for (const h of holdings) {
    // 同主题多 ETF 只处理一次
    if (seenThemes.has(h.themeId)) continue;
    seenThemes.add(h.themeId);

    const t = today.themes.get(h.themeId);
    const y = yesterday.themes.get(h.themeId);
    // 新增或下架主题：静默跳过，不产生事件
    if (!t || !y) continue;

    // 1. 象限切换
    if (t.quadrant !== y.quadrant) {
      events.push({
        event_type:      'theme_quadrant_change',
        theme_id:        h.themeId,
        event_signature: `theme_quadrant_change:${h.themeId}:${today.date}:${y.quadrant}_to_${t.quadrant}`,
        payload:         { from: y.quadrant, to: t.quadrant },
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
          theme_id:        h.themeId,
          event_signature: `theme_strength_cross_up:${h.themeId}:${today.date}:${threshold}`,
          payload:         { threshold, from: yComp, to: tComp },
          asof_date:       today.date,
        });
      }
      if (yComp >= threshold && tComp < threshold) {
        events.push({
          event_type:      'theme_strength_cross_down',
          theme_id:        h.themeId,
          event_signature: `theme_strength_cross_down:${h.themeId}:${today.date}:${threshold}`,
          payload:         { threshold, from: yComp, to: tComp },
          asof_date:       today.date,
        });
      }
    }

    // 3. 信号变化（null 视为无信号，不产生事件）
    if (t.signal !== y.signal && t.signal !== null && y.signal !== null) {
      events.push({
        event_type:      'theme_signal_change',
        theme_id:        h.themeId,
        event_signature: `theme_signal_change:${h.themeId}:${today.date}:${y.signal}_to_${t.signal}`,
        payload:         { from: y.signal, to: t.signal },
        asof_date:       today.date,
      });
    }
  }

  return events;
}
