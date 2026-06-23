// frontend/src/lib/portfolio/eventDisplay.ts
// 事件渲染纯函数 — 无副作用，无依赖网络/DB；与 UI 框架解耦便于单测。
//
// 设计立场：事件在 DB 里是冻结的历史快照 (payload.etf_codes 是触发瞬间的持仓)。
//   UI 显示「事件影响了你 *当前* 持仓的 SOXX」需要实时与 currentHoldings 做交集，
//   这是渲染层的事，不应回写 DB（参见 eventTypes.ts 顶部注释）。

import type { UserEvent } from './eventTypes';

/**
 * 计算事件 etf_codes 与当前持仓的交集情况，返回 UI 文案。
 *
 * - 触发时持有 + 现仍持有 → 「影响你持仓的 SOXX, SMH」
 * - 触发时持有 + 现已卖出 → 「曾涉及你持仓的 SOXX（已卖出）」
 * - payload 无 etf_codes (空数组)  → null（UI 决定降级到主题级提示或不显示）
 *
 * @param event           事件行（含 payload.etf_codes）
 * @param currentHoldings 当前持仓 ETF 代码集合（O(1) 查询）
 */
export function formatAffectedEtfs(
  event:            UserEvent,
  currentHoldings:  Set<string>,
): string | null {
  const codes = event.payload.etf_codes;
  if (codes.length === 0) return null;

  const stillHeld = codes.filter(c => currentHoldings.has(c));
  if (stillHeld.length > 0) {
    return `影响你持仓的 ${stillHeld.join(', ')}`;
  }
  return `曾涉及你持仓的 ${codes.join(', ')}（已卖出）`;
}
