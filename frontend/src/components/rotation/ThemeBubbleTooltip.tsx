import type { Theme } from '@/types/themes';

const pct = (v: number | null): string => {
  if (v === null) return '-';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(2)}%`;
};

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload?: { themeId?: string } }>;
  theme: Theme;
}

export const ThemeBubbleTooltip = ({ active, payload, theme }: TooltipProps) => {
  if (!active || !payload || payload.length === 0) return null;
  const { strength, rank, returns, tags, primary_us, us_etfs } = theme;
  const otherEtfs = us_etfs.filter(e => e !== primary_us).join(', ');

  return (
    <div className="bg-white border rounded shadow-lg p-3 text-xs space-y-2 max-w-xs">
      <div className="font-bold text-sm">{theme.name}</div>
      <div className="border-t pt-2 space-y-1">
        <div className="flex justify-between"><span>综合排名 #{rank.composite}</span><span>composite {strength.composite}</span></div>
        <div className="flex justify-between"><span>短期(1d) #{rank.short}</span><span>strength.short {strength.short}</span></div>
        <div className="flex justify-between"><span>中期(5d) #{rank.mid}</span><span>strength.mid {strength.mid}</span></div>
        <div className="flex justify-between"><span>长期(60d) #{rank.long}</span><span>strength.long {strength.long}</span></div>
      </div>
      <div className="border-t pt-2 grid grid-cols-2 gap-x-2 gap-y-0.5">
        <div>1d: {pct(returns.r_1d)}</div>
        <div>5d: {pct(returns.r_5d)}</div>
        <div>20d: {pct(returns.r_20d)}</div>
        <div>60d: {pct(returns.r_60d)}</div>
        <div className="col-span-2">YTD: {pct(returns.r_ytd)}</div>
      </div>
      <div className="border-t pt-2 space-y-0.5">
        <div>标签: {tags.join(', ')}</div>
        <div>主 ETF: {primary_us}{otherEtfs && ` + ${otherEtfs}`}</div>
      </div>
    </div>
  );
};
