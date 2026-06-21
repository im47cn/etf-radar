import { KpiCards } from './KpiCards';
import { StaleBanner } from './StaleBanner';
import { UpdateBadge } from './UpdateBadge';
import { RadarTabs } from './RadarTabs';
import { UserMenu } from './UserMenu';

export const Header = () => (
  <header className="border-b bg-white p-4 space-y-3">
    <div className="flex items-center justify-between">
      <div>
        <div className="text-xl font-bold">ETF Radar</div>
        <div className="text-xs text-gray-500">
          追踪美股主题 → 映射 A 股 ETF 联动信号
        </div>
      </div>
      <div className="flex items-center gap-3">
        <UpdateBadge />
        <UserMenu />
      </div>
    </div>
    <RadarTabs />
    <KpiCards />
    <StaleBanner />
  </header>
);
