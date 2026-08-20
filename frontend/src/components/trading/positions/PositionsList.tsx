import { useTrades } from '@/hooks/useTrades';

/** 当前持仓表：代码/名称/股数/成本/当前止损位，由交易事件流推导（derivePositions）。事实性展示。 */
export const PositionsList = () => {
  const { positions } = useTrades();

  if (positions.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-500">
        暂无持仓：在下方「交易记录录入」记入开仓事件后，此处按事件流自动汇总当前持仓、
        加权平均成本与最近记录的止损参考位。
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="min-w-full bg-gray-900 text-left text-xs text-gray-200">
        <thead>
          <tr className="border-b border-gray-700 bg-gray-800 text-gray-400">
            <th className="px-2 py-2 font-medium">代码</th>
            <th className="px-2 py-2 font-medium">名称</th>
            <th className="px-2 py-2 font-medium">股数</th>
            <th className="px-2 py-2 font-medium">成本价</th>
            <th className="px-2 py-2 font-medium">当前止损位</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            // 止损 null → '—'：提 const 避免 JSX 内 ?? 的 coverage 盲区
            const stopLabel = p.stop_current != null ? p.stop_current.toFixed(2) : '—';
            return (
              <tr key={p.code} className="border-b border-gray-800 hover:bg-gray-800/60">
                <td className="px-2 py-1.5 font-mono text-gray-400">{p.code}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">{p.name}</td>
                <td className="px-2 py-1.5">{p.shares}</td>
                <td className="px-2 py-1.5">{p.avg_cost.toFixed(2)}</td>
                <td className="px-2 py-1.5">{stopLabel}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
