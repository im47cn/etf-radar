import { useMemo } from 'react';
import { useDataContext } from '@/providers/DataProvider';
import { useUIState } from '@/providers/UIStateProvider';
import { EtfRow } from './EtfRow';
import type { Etf } from '@/types/etfs';
import type { PairSignal } from '@/types/signals';

export const CnEtfTable = () => {
  const { etfs, signals } = useDataContext();
  const { state } = useUIState();

  const rows = useMemo<Array<{ pair: PairSignal; etf: Etf }>>(() => {
    if (!etfs || !signals || !state.selectedThemeId) return [];
    const pairsForTheme = signals.pair_signals.filter(
      (p) => p.theme_id === state.selectedThemeId,
    );
    return pairsForTheme
      .map((p) => {
        const etf = etfs.etfs.find((e) => e.code === p.cn_code);
        return etf ? { pair: p, etf } : null;
      })
      .filter((r): r is { pair: PairSignal; etf: Etf } => r !== null);
  }, [etfs, signals, state.selectedThemeId]);

  if (!state.selectedThemeId) return null;

  return (
    <div className="bg-white border rounded mt-4">
      <div className="p-3 border-b">
        <div className="font-medium">A股场内ETF候选池</div>
        <div className="text-xs text-gray-500">
          随当前主题联动筛选, 显示映射分、强弱与流动性
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-600">
            <tr>
              <th className="px-2 py-2 text-left">名称</th>
              <th className="px-2 py-2 text-left">代码</th>
              <th className="px-2 py-2 text-left">映射</th>
              <th className="px-2 py-2 text-right">1日</th>
              <th className="px-2 py-2 text-right">5日</th>
              <th className="px-2 py-2 text-right">20日</th>
              <th className="px-2 py-2 text-right">60日</th>
              <th className="px-2 py-2 text-right">120日</th>
              <th className="px-2 py-2 text-right">成交额</th>
              <th className="px-2 py-2 text-center">状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <EtfRow key={r.etf.code + '-' + i} etf={r.etf} pair={r.pair} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
