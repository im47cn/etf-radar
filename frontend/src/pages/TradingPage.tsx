import { useSearchParams } from 'react-router-dom';
import { FeatureGate } from '@/components/gate/FeatureGate';
import { EnvironmentTab } from '@/components/trading/EnvironmentTab';
import { SignalsTab } from '@/components/trading/SignalsTab';
import { PositionsTab } from '@/components/trading/positions/PositionsTab';
import { ReviewsTab } from '@/components/trading/review/ReviewsTab';
import { WatchlistPage } from '@/pages/WatchlistPage';
import { PortfolioPage } from '@/pages/PortfolioPage';

/** 六 Tab 页壳: 环境(免费) / 信号🔒 / 自选🔒 / 持仓🔒 / 主题持仓(auth 开放) / 复盘🔒. */
type TabKey = 'env' | 'signals' | 'watchlist' | 'positions' | 'holdings' | 'review';

const TABS: { key: TabKey; label: string; locked: boolean }[] = [
  { key: 'env', label: '环境', locked: false },
  { key: 'signals', label: '信号', locked: true },
  { key: 'watchlist', label: '自选', locked: true },
  { key: 'positions', label: '持仓', locked: true },
  { key: 'holdings', label: '主题持仓', locked: false },
  { key: 'review', label: '复盘', locked: true },
];

const isTabKey = (k: string | null): k is TabKey => TABS.some((t) => t.key === k);

const tabBtn = (active: boolean): string =>
  active
    ? 'px-3 py-1 rounded bg-blue-600 text-white text-sm transition-all duration-150'
    : 'px-3 py-1 rounded text-gray-700 hover:bg-gray-100 text-sm transition-all duration-150 active:scale-95';

export const TradingPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const tab: TabKey = isTabKey(tabParam) ? tabParam : 'env';
  const selectTab = (key: TabKey) => setSearchParams({ tab: key }, { replace: true });

  return (
    <main className="flex flex-col gap-4 p-4 animate-crossfade">
      <div className="flex items-center justify-between animate-fade-rise" style={{ animationDelay: '0ms' }}>
        <h1 className="text-lg font-semibold text-gray-800">交易</h1>
        <div className="flex gap-1" role="tablist" aria-label="交易页 Tab">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={tabBtn(tab === t.key)}
              onClick={() => selectTab(t.key)}
            >
              {t.label}
              {t.locked && <span aria-hidden>🔒</span>}
            </button>
          ))}
        </div>
      </div>

      {tab === 'env' && <EnvironmentTab />}

      {tab === 'signals' && (
        <FeatureGate copy="trading-signals" required="member">
          <SignalsTab />
        </FeatureGate>
      )}

      {tab === 'watchlist' && <WatchlistPage />}

      {tab === 'positions' && (
        <FeatureGate copy="trading-positions" required="member">
          <PositionsTab />
        </FeatureGate>
      )}

      {tab === 'holdings' && <PortfolioPage />}

      {tab === 'review' && (
        <FeatureGate copy="trading-review" required="member">
          <ReviewsTab />
        </FeatureGate>
      )}

      <p className="text-xs text-gray-400 animate-fade-rise" style={{ animationDelay: '120ms' }}>
        口径说明：趋势模板（8 条）/ 四阶段 / VCP 形态 / 买区与止损位均为既定规则的事实性计算结果展示，
        状态文案不构成买卖指令；仓位计算器为纯算术。本页不构成投资建议。
      </p>
    </main>
  );
};
