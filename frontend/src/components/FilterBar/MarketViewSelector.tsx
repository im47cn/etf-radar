import { useUIState } from '@/providers/uiStateContext';
import type { MarketView } from '@/lib/marketView';

const OPTIONS: { v: MarketView; label: string }[] = [
  { v: 'us', label: '美股' },
  { v: 'cn-all', label: 'A股' },
];

export const MarketViewSelector = () => {
  const { state, dispatch } = useUIState();
  return (
    <div
      role="group"
      aria-label="市场视角"
      className="inline-flex rounded border border-slate-200 overflow-hidden text-sm"
    >
      {OPTIONS.map(({ v, label }) => {
        const active = state.marketView === v;
        return (
          <button
            key={v}
            type="button"
            aria-pressed={active}
            onClick={() => dispatch({ type: 'SET_MARKET_VIEW', v })}
            className={
              'px-3 py-1 transition-colors ' +
              (active
                ? 'bg-slate-800 text-white'
                : 'bg-white text-slate-600 hover:bg-slate-100')
            }
          >
            {label}
          </button>
        );
      })}
    </div>
  );
};
