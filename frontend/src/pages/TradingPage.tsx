import { useState } from 'react';
import { FeatureGate } from '@/components/gate/FeatureGate';
import { EnvironmentTab } from '@/components/trading/EnvironmentTab';
import { SignalsTab } from '@/components/trading/SignalsTab';
import { PositionsTab } from '@/components/trading/positions/PositionsTab';
import { ReviewsTab } from '@/components/trading/review/ReviewsTab';

/** 四 Tab 页壳: 环境(免费) / 信号🔒 / 持仓🔒 / 复盘🔒. */
type TabKey = 'env' | 'signals' | 'positions' | 'review';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'env', label: '环境' },
  { key: 'signals', label: '信号' },
  { key: 'positions', label: '持仓' },
  { key: 'review', label: '复盘' },
];

const tabBtn = (active: boolean): string =>
  active
    ? 'px-3 py-1 rounded bg-blue-600 text-white text-sm transition-all duration-150'
    : 'px-3 py-1 rounded text-gray-700 hover:bg-gray-100 text-sm transition-all duration-150 active:scale-95';

export const TradingPage = () => {
  const [tab, setTab] = useState<TabKey>('env');

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
              onClick={() => setTab(t.key)}
            >
              {t.label}
              {t.key !== 'env' && <span aria-hidden>🔒</span>}
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

      {tab === 'positions' && (
        <FeatureGate copy="trading-positions" required="member">
          <PositionsTab />
        </FeatureGate>
      )}

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
