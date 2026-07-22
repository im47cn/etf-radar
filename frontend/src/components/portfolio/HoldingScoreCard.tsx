import type { HoldingScore } from '@/lib/portfolio/types';
import { useHoldingScoreCard } from '@/hooks/useHoldingScoreCard';
import { HoldingScoreCardActions } from './HoldingScoreCardActions';
import { HoldingScoreCardIndicators } from './HoldingScoreCardIndicators';
import { HoldingScoreCardPosition } from './HoldingScoreCardPosition';
import { HoldingScoreCardSignals } from './HoldingScoreCardSignals';

interface Props {
  score:    HoldingScore;
  onDelete: (etfCode: string) => void;
  onEdit?:  (etfCode: string) => void;
}

export const HoldingScoreCard = ({ score, onDelete, onEdit }: Props) => {
  const isUncovered = score.status === 'uncovered';
  const { menuOpen, setMenuOpen, menuRef, handleDelete, handleEdit } = useHoldingScoreCard({
    etfCode: score.etfCode,
    onDelete,
    onEdit,
  });

  return (
    <div className={`border rounded-lg p-4 ${isUncovered ? 'bg-gray-50 opacity-90' : 'bg-white'}`}>
      {/* Header */}
      <div className="flex justify-between items-start mb-2">
        <div>
          <div className="font-semibold">{score.etfCode}</div>
          {score.name && <div className="text-sm text-gray-600">{score.name}</div>}
        </div>
        <div className="flex flex-wrap gap-1 items-start">
          <HoldingScoreCardIndicators
            isUncovered={isUncovered}
            l2Tag={score.l2Tag}
            momentumTag={score.momentumTag}
          />
          <HoldingScoreCardActions
            menuOpen={menuOpen}
            menuRef={menuRef}
            onToggle={() => setMenuOpen(o => !o)}
            onEditClick={onEdit ? handleEdit : undefined}
            onDeleteClick={handleDelete}
          />
        </div>
      </div>

      {/* 持仓 */}
      <HoldingScoreCardPosition
        shares={score.shares}
        costPrice={score.costPrice}
        currentPrice={score.currentPrice}
        marketValue={score.marketValue}
        pnlAbs={score.pnlAbs}
        pnlPct={score.pnlPct}
      />

      {/* uncovered 提示 */}
      {isUncovered && (
        <div className="mt-3 pt-2 border-t text-xs text-gray-500">
          ⓘ 该 ETF 不在信号覆盖范围（14 主题外），仅记录持仓信息
        </div>
      )}

      {/* covered: 信号区 */}
      {!isUncovered && (
        <HoldingScoreCardSignals
          themeName={score.themeName}
          secondaryThemes={score.secondaryThemes}
          selfStrength={score.selfStrength}
          themeUsStrength={score.themeUsStrength}
          themeCnStrength={score.themeCnStrength}
          narrative={score.narrative}
        />
      )}
    </div>
  );
};
