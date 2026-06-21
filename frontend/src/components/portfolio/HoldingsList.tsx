import { useState } from 'react';
import { useHoldings } from '@/hooks/useHoldings';
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
import { HoldingScoreCard } from './HoldingScoreCard';
import { HoldingsEditor } from './HoldingsEditor';
import { PortfolioSummary } from './PortfolioSummary';

export const HoldingsList = () => {
  const { remove } = useHoldings();
  const { scores, loading } = usePortfolioScores();
  const [editorOpen, setEditorOpen] = useState(false);

  if (loading) {
    return <div className="p-8 text-center text-gray-500">加载持仓...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">我的持仓（{scores.length} 只）</h2>
        <button
          onClick={() => setEditorOpen(true)}
          className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm"
        >+ 添加持仓</button>
      </div>

      {scores.length === 0 ? (
        <div className="border rounded p-8 text-center bg-gray-50">
          <div className="text-gray-600 mb-2">还没有录入持仓</div>
          <div className="text-sm text-gray-500 mb-4">
            把您的 A 股 ETF 接入信号引擎，看看它们当下状态
          </div>
          <button
            onClick={() => setEditorOpen(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded"
          >+ 添加第一只</button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {scores.map(s => (
              <HoldingScoreCard key={s.etfCode} score={s} onDelete={remove} />
            ))}
          </div>
          <PortfolioSummary scores={scores} />
        </>
      )}

      <HoldingsEditor open={editorOpen} onClose={() => setEditorOpen(false)} />
    </div>
  );
};
