// 强弱/动量标签 → Tailwind 配色，HoldingScoreCard 与 OpportunityCard 共用同一套映射
export const tagColor = (tag?: string): string => {
  switch (tag) {
    case '偏强':       return 'bg-green-100 text-green-700';
    case '中性偏强':   return 'bg-green-50 text-green-600';
    case '中性偏弱':   return 'bg-orange-50 text-orange-600';
    case '偏弱':       return 'bg-red-100 text-red-700';
    case '动量向上':   return 'bg-blue-100 text-blue-700';
    case '动量向下':   return 'bg-amber-100 text-amber-700';
    default:           return 'bg-gray-100 text-gray-600';
  }
};
