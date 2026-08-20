import { useTrades } from '@/hooks/useTrades';
import { Skeleton } from '@/components/ui/skeleton';
import { PositionsList } from './PositionsList';
import { TradeEntryForm } from './TradeEntryForm';
import { TradesLog } from './TradesLog';
import { TradingSettingsPanel } from './TradingSettingsPanel';

/**
 * 持仓管理 Tab：当前持仓 + 交易录入 + 事件流 + 风控参数。
 * 全部为记账与事实性状态展示（合规立场 §0：无买卖指令词汇）。
 * 会员门内挂载（FeatureGate required=member，见 TradingPage）。
 */
export const PositionsTab = () => {
  const { loading, error } = useTrades();

  if (loading) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="加载中">
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {error != null && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          交易数据加载失败：{error}
        </div>
      )}
      <PositionsList />
      <TradeEntryForm />
      <TradesLog />
      <TradingSettingsPanel />
      <p className="text-xs text-gray-400">
        口径说明：当前持仓由您录入的交易事件流推导（加仓按加权平均成本，减仓不改变剩余持仓成本）；
        「当前止损位」为最近一笔交易记录携带的止损参考位，仅为事实记录。本页为记账与状态展示工具，
        不构成买卖指令或投资建议。
      </p>
    </div>
  );
};
