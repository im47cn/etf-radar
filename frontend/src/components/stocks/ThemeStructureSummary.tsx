import { useMemo } from 'react';
import type { AggregatedStock } from '@/types/holdings';
import { diagnoseStructure } from '@/lib/stocks/structureInsight';

interface Props {
  stocks: AggregatedStock[];
}

const STRUCTURE_COLOR: Record<string, string> = {
  head_led: 'border-orange-300 bg-orange-50 text-orange-900',
  broad_strength: 'border-red-300 bg-red-50 text-red-900',
  divergent: 'border-yellow-300 bg-yellow-50 text-yellow-900',
  weak: 'border-blue-300 bg-blue-50 text-blue-900',
  no_data: 'border-gray-300 bg-gray-50 text-gray-600',
};

export const ThemeStructureSummary = ({ stocks }: Props) => {
  const diag = useMemo(() => diagnoseStructure(stocks), [stocks]);
  const threeStarCount = useMemo(
    () => stocks.filter(s => s.indicators?.leader === '⭐⭐⭐').length,
    [stocks],
  );
  const total = stocks.length;
  const ratioPct = total > 0 ? Math.round((threeStarCount / total) * 100) : 0;

  return (
    <div
      className={`mb-3 p-3 border rounded ${STRUCTURE_COLOR[diag.type] ?? STRUCTURE_COLOR.no_data}`}
      aria-label="主题结构摘要"
    >
      <div className="text-sm font-medium">{diag.text}</div>
      {diag.type !== 'no_data' && (
        <div className="mt-1 text-xs text-gray-600">
          <span>⭐⭐⭐ {threeStarCount} 只 ({ratioPct}%)</span>
          {diag.meanStrength !== null && (
            <span className="ml-3">均值强度 {diag.meanStrength}</span>
          )}
        </div>
      )}
    </div>
  );
};
