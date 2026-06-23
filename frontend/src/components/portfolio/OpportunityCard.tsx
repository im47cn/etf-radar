import { Link } from 'react-router-dom';
import type { Opportunity } from '@/lib/portfolio/types';

interface Props {
  opp: Opportunity;
}

const tagColor = (tag?: string) => {
  switch (tag) {
    case '偏强':       return 'bg-green-100 text-green-700 border-green-200';
    case '中性偏强':   return 'bg-green-50 text-green-600 border-green-100';
    case '中性偏弱':   return 'bg-orange-50 text-orange-600 border-orange-100';
    case '偏弱':       return 'bg-red-100 text-red-700 border-red-200';
    default:           return 'bg-gray-100 text-gray-600 border-gray-200';
  }
};

/**
 * 单只机会候选卡。仅展示信号事实（强度分位 + L2 形容词标签），
 * 不出现任何买卖指令性语言（无"推荐买入/建议加仓"等）。
 * 点击"查看详情"跳 RadarPage 并选中该主题。
 */
export const OpportunityCard = ({ opp }: Props) => {
  return (
    <div className="border rounded-lg p-3 bg-white hover:shadow-sm transition">
      <div className="flex items-center justify-between mb-2">
        <div className="font-medium">{opp.themeName}</div>
        <span className={`text-xs px-1.5 py-0.5 rounded border ${tagColor(opp.l2Tag)}`}>
          {opp.l2Tag}
        </span>
      </div>

      <div className="text-xs text-gray-500 mb-2">
        主映射 ETF：{opp.primaryCn}
      </div>

      <div className="grid grid-cols-4 gap-1 text-xs text-center mb-2">
        <div>
          <div className="text-gray-400">短</div>
          <div className="font-mono">{opp.strength.short}</div>
        </div>
        <div>
          <div className="text-gray-400">中</div>
          <div className="font-mono">{opp.strength.mid}</div>
        </div>
        <div>
          <div className="text-gray-400">长</div>
          <div className="font-mono">{opp.strength.long}</div>
        </div>
        <div>
          <div className="text-gray-400">综合</div>
          <div className="font-mono font-semibold">{opp.strength.composite}</div>
        </div>
      </div>

      {opp.momentumTag && (
        <div className="text-xs text-amber-700 mb-2">{opp.momentumTag}</div>
      )}

      <Link
        to={{ pathname: '/', search: `?theme=${opp.themeId}` }}
        className="block text-center text-xs text-blue-600 hover:underline mt-1"
      >
        查看详情 →
      </Link>
    </div>
  );
};
