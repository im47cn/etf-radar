import { rsiColor } from '@/lib/stocks/indicatorThresholds';
import { cn } from '@/lib/utils';

interface Props {
  value: number | null;
  className?: string;
}

export const RSIBadge = ({ value, className }: Props) => {
  if (value === null || Number.isNaN(value)) {
    return <span className="text-gray-400">—</span>;
  }
  return (
    <span
      className={cn(
        'inline-block px-2 py-0.5 rounded text-xs font-mono tabular-nums',
        rsiColor(value),
        className,
      )}
    >
      {value.toFixed(1)}
    </span>
  );
};
