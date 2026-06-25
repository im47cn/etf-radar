import { strengthTier } from '@/lib/stocks/indicatorThresholds';
import { cn } from '@/lib/utils';

interface Props {
  value: number | null;
  className?: string;
}

export const StrengthBadge = ({ value, className }: Props) => {
  if (value === null || Number.isNaN(value)) {
    return <span className="text-gray-400">—</span>;
  }
  const tier = strengthTier(value);
  return (
    <span
      title={tier.label}
      className={cn(
        'inline-block px-2 py-0.5 rounded text-xs font-mono tabular-nums',
        tier.color,
        className,
      )}
    >
      {value}
    </span>
  );
};
