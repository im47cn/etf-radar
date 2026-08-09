/**
 * 门控页面 key 词典（共享）。
 *
 * FeatureGate 的文案预设 GATE_COPY 以此为 key，保证每个门控页有对应的 hero 文案。
 * 新增门控页：在 GATED_PAGES 加一项，再在 FeatureGate.tsx 的 GATE_COPY 补文案。
 */
export const GATED_PAGES = ['portfolio', 'watchlist', 'evidence', 'membership'] as const;

export type GatedPage = (typeof GATED_PAGES)[number];
