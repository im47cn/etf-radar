import type { Etf } from '@/types/etfs';
import type { PairSignal, SignalType } from '@/types/signals';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { formatPct, formatYi } from '@/lib/format';
import { cn } from '@/lib/utils';

const SIGNAL_LABEL: Record<SignalType, string> = {
  resonance: '共振',
  transmission: '传导',
  divergence: '背离',
};

const pctCls = (v: number | null): string =>
  (v ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600';

export const EtfRow = ({ etf, pair }: { etf: Etf; pair: PairSignal | undefined }) => (
  <tr className="border-t">
    <td className="px-2 py-2">
      <div className="text-sm font-medium">{etf.name}</div>
      <div className="text-xs text-gray-500">{etf.tracking_index}</div>
    </td>
    <td className="px-2 py-2 text-sm">{etf.code}</td>
    <td className="px-2 py-2 w-24">
      {pair?.mapping_score != null ? (
        <div className="flex items-center gap-1">
          <Progress value={pair.mapping_score} className="h-2 flex-1" />
          <span className="text-xs w-6 text-right">{pair.mapping_score}</span>
        </div>
      ) : (
        <span className="text-gray-400">—</span>
      )}
    </td>
    <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_1d))}>
      {formatPct(etf.returns.r_1d)}
    </td>
    <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_5d))}>
      {formatPct(etf.returns.r_5d)}
    </td>
    <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_20d))}>
      {formatPct(etf.returns.r_20d)}
    </td>
    <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_60d))}>
      {formatPct(etf.returns.r_60d)}
    </td>
    <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_120d))}>
      {formatPct(etf.returns.r_120d)}
    </td>
    <td className="px-2 py-2 text-right text-xs">{formatYi(etf.amount_yi)}</td>
    <td className="px-2 py-2 text-center">
      {pair?.signal && <Badge>{SIGNAL_LABEL[pair.signal]}</Badge>}
    </td>
  </tr>
);
