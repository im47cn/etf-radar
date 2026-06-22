import { useLocation } from 'react-router-dom';
import { KpiCards } from './KpiCards';
import { StaleBanner } from './StaleBanner';
import { UpdateBadge } from './UpdateBadge';
import { RadarTabs } from './RadarTabs';
import { UserMenu } from './UserMenu';

export const Header = () => {
  const { pathname } = useLocation();
  // KpiCards 概念上属于跨市雷达 (共振/传导/背离 等跨市统计),
  // 主题轮动 / 我的持仓 tab 上是噪声 - 仅在 "/" 显示.
  // StaleBanner / UpdateBadge 是全局数据健康指示, 保留在所有 tab.
  const isRadarTab = pathname === '/';

  return (
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
      {isRadarTab && <KpiCards />}
      <StaleBanner />
    </header>
  );
};
