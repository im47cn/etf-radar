import { useMemo, useState } from 'react';
import type { ThemeMetric } from '@/lib/portfolio/types';
import {
  scanOpportunities,
  COMPOSITE_MIN,
  SHORT_MIN,
} from '@/lib/portfolio/scanner';
import { OpportunityCard } from './OpportunityCard';

interface Props {
  themes: ThemeMetric[];
  ownedThemeIds: Set<string>;
}

/**
 * 持仓页底部"信号扫描"折叠面板：
 *   - 默认折叠（主区是持仓体检，扫描为附加视角）
 *   - 候选数 0 时仍渲染面板，展开后给空态文案
 *   - 阈值文案显式告知用户筛选条件（非黑盒）
 */
export const OpportunityScanner = ({ themes, ownedThemeIds }: Props) => {
  const [open, setOpen] = useState(false);

  const opportunities = useMemo(
    () => scanOpportunities(themes, ownedThemeIds),
    [themes, ownedThemeIds],
  );

  return (
    <section className="mt-6 border rounded-lg bg-gray-50">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="font-medium">
          {`信号扫描(${opportunities.length})`}
        </span>
        <span className="text-xs text-gray-500">{open ? '收起 ▲' : '展开 ▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4">
          <div className="text-xs text-gray-500 mb-3">
            筛选条件：综合强度 ≥ {COMPOSITE_MIN} 且 短周期 ≥ {SHORT_MIN}，
            排除您已持仓的主题。仅供信号参考，不构成投资建议。
          </div>

          {opportunities.length === 0 ? (
            <div className="text-sm text-gray-500 text-center py-6">
              当前无满足筛选条件的主题——可能强势主题已在您的持仓中，
              或全市场暂无新的发力主题。
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {opportunities.map(opp => (
                <OpportunityCard key={opp.themeId} opp={opp} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
