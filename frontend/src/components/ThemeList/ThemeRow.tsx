// FIXME(market-view-global): returns 列暂仍取 theme.returns (主 ETF 数据);
// cn-* 视角下严格应为 primary_cn 的 returns, 需新增 returns_us/returns_cn 字段, 超出本 PR 范围.
import type { Theme, DimName } from '@/types/themes';
import type { ThemeSignal, SignalType } from '@/types/signals';
import type { MarketView } from '@/lib/marketView';
import { isCnOnly, pickStrength } from '@/lib/marketView';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { formatPct, formatStrength } from '@/lib/format';
import { cn } from '@/lib/utils';

interface Props {
  index: number;
  theme: Theme;
  signal: ThemeSignal | undefined;
  dimension: DimName;
  marketView: MarketView;
  selected: boolean;
  onClick: () => void;
}

const SIGNAL_LABEL: Record<SignalType, string> = {
  resonance: '共振',
  transmission: '传导',
  divergence: '背离',
};

const signalVariant = (s: SignalType | null | undefined): 'default' | 'secondary' | 'destructive' => {
  if (s === 'divergence') return 'destructive';
  if (s === 'transmission') return 'secondary';
  return 'default';
};

export const ThemeRow = ({ index, theme, signal, dimension, marketView, selected, onClick }: Props) => {
  const strength = pickStrength(theme, marketView)?.[dimension];
  const r1d = theme.returns.r_1d;
  const r5d = theme.returns.r_5d;
  const primaryEtf = marketView === 'us' ? theme.primary_us : theme.primary_cn;
  return (
    <tr
      onClick={onClick}
      className={cn(
        'cursor-pointer hover:bg-gray-50 border-l-2 border-transparent',
        selected && 'border-blue-600 bg-blue-50',
      )}
    >
      <td className="px-2 py-2 text-center">
        <span
          className={cn(
            'inline-flex items-center justify-center w-6 h-6 rounded-full text-xs',
            index < 3 ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-600',
          )}
        >
          {(index + 1).toString().padStart(2, '0')}
        </span>
      </td>
      <td className="px-2 py-2">
        <div className="font-medium">
          {theme.name}
          {isCnOnly(theme) && (
            <span className="ml-2 inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-slate-100 text-slate-600 border border-slate-200">
              A股专属
            </span>
          )}
        </div>
        <div className="text-xs text-gray-500">{theme.us_etfs.join(' / ')}</div>
      </td>
      <td className="px-2 py-2 text-xs">{primaryEtf ?? '—'}</td>
      <td className="px-2 py-2 w-32">
        <div className="flex items-center gap-2">
          <Progress value={strength ?? 0} className="h-2 flex-1" />
          <span className="text-sm font-medium w-8 text-right">{formatStrength(strength)}</span>
        </div>
      </td>
      <td
        className={cn(
          'px-2 py-2 text-right text-xs',
          (r1d ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600',
        )}
      >
        {formatPct(r1d)}
      </td>
      <td
        className={cn(
          'px-2 py-2 text-right text-xs',
          (r5d ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600',
        )}
      >
        {formatPct(r5d)}
      </td>
      <td className="px-2 py-2 text-center">
        {signal?.signal && (
          <Badge variant={signalVariant(signal.signal)}>{SIGNAL_LABEL[signal.signal]}</Badge>
        )}
      </td>
    </tr>
  );
};
