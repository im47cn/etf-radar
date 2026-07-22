interface Props {
  shares: number;
  costPrice: number | null;
  currentPrice: number | null;
  marketValue: number | null;
  pnlAbs: number | null;
  pnlPct: number | null;
}

const fmtPct = (n: number | null) => n === null ? '—' : `${(n * 100).toFixed(1)}%`;
const fmtMoney = (n: number | null) => n === null ? '—' : `¥${n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;

export const HoldingScoreCardPosition = ({ shares, costPrice, currentPrice, marketValue, pnlAbs, pnlPct }: Props) => (
  <div className="text-sm space-y-1 border-t pt-2">
    <div>持仓 {shares} 份 {costPrice !== null && `· 成本 ${fmtMoney(costPrice)}`}</div>
    {currentPrice !== null && (
      <div>现价 {fmtMoney(currentPrice)} · 市值 {fmtMoney(marketValue)}</div>
    )}
    {pnlAbs !== null && pnlPct !== null && (
      <div className={pnlAbs >= 0 ? 'text-green-600' : 'text-red-600'}>
        盈亏 {pnlAbs >= 0 ? '+' : ''}{fmtMoney(pnlAbs)} ({pnlAbs >= 0 ? '+' : ''}{fmtPct(pnlPct)})
      </div>
    )}
  </div>
);
