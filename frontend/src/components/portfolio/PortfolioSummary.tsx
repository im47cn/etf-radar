import type { HoldingScore } from '@/lib/portfolio/types';

interface Props {
  scores: HoldingScore[];
}

export const PortfolioSummary = ({ scores }: Props) => {
  const covered = scores.filter(s => s.status === 'covered');
  const uncovered = scores.filter(s => s.status === 'uncovered');

  const totalMV = covered.reduce((sum, s) => sum + (s.marketValue ?? 0), 0);
  const totalPnl = covered
    .filter(s => s.pnlAbs !== null)
    .reduce((sum, s) => sum + (s.pnlAbs ?? 0), 0);
  const totalCost = covered
    .filter(s => s.pnlAbs !== null)
    .reduce((sum, s) => sum + ((s.marketValue ?? 0) - (s.pnlAbs ?? 0)), 0);
  const totalPnlPct = totalCost > 0 ? totalPnl / totalCost : null;

  const counts = {
    '偏强':     covered.filter(s => s.l2Tag === '偏强').length,
    '中性偏强': covered.filter(s => s.l2Tag === '中性偏强').length,
    '中性偏弱': covered.filter(s => s.l2Tag === '中性偏弱').length,
    '偏弱':     covered.filter(s => s.l2Tag === '偏弱').length,
  };

  if (scores.length === 0) return null;

  return (
    <div className="border-t border-b py-4 my-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
      <div>
        <div className="text-gray-500">总市值</div>
        <div className="font-semibold text-lg">¥{totalMV.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</div>
        {uncovered.length > 0 && (
          <div className="text-xs text-gray-400">另含 {uncovered.length} 只无估值持仓</div>
        )}
      </div>
      <div>
        <div className="text-gray-500">总盈亏</div>
        <div className={`font-semibold text-lg ${totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
          {totalPnl >= 0 ? '+' : ''}¥{Math.abs(totalPnl).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
        </div>
        {totalPnlPct !== null && (
          <div className={`text-xs ${totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {totalPnl >= 0 ? '+' : ''}{(totalPnlPct * 100).toFixed(1)}%
          </div>
        )}
      </div>
      <div>
        <div className="text-gray-500">覆盖率</div>
        <div className="font-semibold text-lg">{covered.length} / {scores.length}</div>
      </div>
      <div>
        <div className="text-gray-500">强弱分布</div>
        <div className="text-xs space-x-2">
          {counts['偏强']     > 0 && <span className="text-green-700">偏强 {counts['偏强']}</span>}
          {counts['中性偏强'] > 0 && <span>中性偏强 {counts['中性偏强']}</span>}
          {counts['中性偏弱'] > 0 && <span>中性偏弱 {counts['中性偏弱']}</span>}
          {counts['偏弱']     > 0 && <span className="text-red-700">偏弱 {counts['偏弱']}</span>}
        </div>
      </div>
    </div>
  );
};
