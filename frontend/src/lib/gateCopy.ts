/**
 * 门控页面 key 词典（共享）。
 *
 * AuthGate 与 MemberGate 的文案预设 key 均从此派生，保证"同一页面在同一 gate 用同一 key"：
 * - AuthGate 覆盖全部门控页（{@link AuthCopyKey} = GatedPage）。
 * - MemberGate 仅覆盖会员功能页（{@link MemberCopyKey} = GatedPage 子集）。
 *
 * 新增门控页：在此加一项，再按需在 AUTH_COPY / MEMBER_COPY 补文案。
 */
export const GATED_PAGES = ['portfolio', 'watchlist', 'evidence', 'membership'] as const;

export type GatedPage = (typeof GATED_PAGES)[number];
