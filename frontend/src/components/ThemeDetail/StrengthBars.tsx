import { Progress } from '@/components/ui/progress';
import type { Strength } from '@/types/themes';

const LABELS: Array<[keyof Strength, string]> = [
  ['short', '短期'],
  ['mid', '中期'],
  ['long', '长期'],
  ['composite', '综合'],
];

export const StrengthBars = ({ strength }: { strength: Strength }) => (
  <div className="space-y-2">
    {LABELS.map(([k, label]) => (
      <div key={k} className="flex items-center gap-2 text-sm">
        <span className="w-12 text-gray-500">{label}</span>
        <Progress value={strength[k]} className="h-2 flex-1" />
        <span className="w-8 text-right font-medium">{strength[k]}</span>
      </div>
    ))}
  </div>
);
