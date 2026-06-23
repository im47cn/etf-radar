import { X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { themesToRotationPoints } from '@/lib/rotation';
import type { Theme } from '@/types/themes';

interface Props {
  theme: Theme | null;
  onClose: () => void;
}

const QUADRANT_NAME: Record<string, string> = {
  leading: '强势',
  rising: '改善',
  lagging: '落后',
  fading: '弱化',
};

const formatPct = (n: number | null): string => {
  if (n === null) return 'N/A';
  const pct = n * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
};

export const FocusedThemePanel = ({ theme, onClose }: Props) => {
  if (!theme) return null;
  const navigate = useNavigate();
  const [pt] = themesToRotationPoints([theme]);
  const quadrantName = pt ? QUADRANT_NAME[pt.quadrant] : '';

  return (
    <section
      className="mt-3 w-full bg-white border border-gray-200 rounded-lg p-4"
      aria-label="主题详情面板"
    >
      <div className="flex justify-between items-start mb-2">
        <h3 className="font-bold text-base">{theme.name}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="text-gray-400 hover:text-gray-600"
        >
          <X size={16} />
        </button>
      </div>
      <div className="text-xs text-gray-500 mb-3">当前象限: {quadrantName}</div>
      <div className="space-y-1 text-sm mb-3">
        <div>
          综合强度: <strong>{theme.strength.composite}</strong> / 排名 <strong>#{theme.rank.composite}</strong>
        </div>
        <div>
          20日涨幅: <strong>{formatPct(theme.returns.r_20d)}</strong>
        </div>
      </div>
      <div className="text-xs text-gray-500 mb-1">关联 ETF (装饰性):</div>
      <div className="flex flex-wrap gap-1">
        {(theme.us_etfs ?? []).map(etf => (
          <span
            key={etf}
            className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs"
          >
            {etf}{etf === theme.primary_us ? ' (primary)' : ''}
          </span>
        ))}
      </div>
      <div className="mt-4 pt-3 border-t border-gray-200">
        <button
          type="button"
          onClick={() => navigate(`/theme/${theme.id}/stocks`)}
          className="text-sm text-blue-600 hover:text-blue-700 hover:underline"
        >
          查看主题成分股 →
        </button>
      </div>
    </section>
  );
};
