import { formatPct } from '@/lib/format';
import type { Returns } from '@/types/themes';

const LABELS: Array<[keyof Returns, string]> = [
  ['r_1d', '1日'],
  ['r_5d', '5日'],
  ['r_20d', '20日'],
  ['r_60d', '60日'],
  ['r_120d', '120日'],
  ['r_ytd', '年初至今'],
];

export const PeriodReturns = ({ returns }: { returns: Returns }) => (
  <div className="grid grid-cols-3 gap-2 text-sm">
    {LABELS.map(([k, label]) => {
      const v = returns[k];
      const cls = (v ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600';
      return (
        <div key={k} className="border rounded p-2">
          <div className="text-xs text-gray-500">{label}</div>
          <div className={cls}>{formatPct(v)}</div>
        </div>
      );
    })}
  </div>
);
