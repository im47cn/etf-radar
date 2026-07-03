import { StaleBanner } from './StaleBanner';
import { UpdateBadge } from './UpdateBadge';
import { RadarTabs } from './RadarTabs';
import { UserMenu } from './UserMenu';
import { EventBadge } from './EventBadge';

export const Header = () => (
  <header className="border-b bg-white p-4 space-y-3">
    <div className="flex items-center justify-between">
      <div>
        <div className="text-xl font-bold">ETF Radar</div>
      </div>
      <div className="flex items-center gap-3">
        <UpdateBadge />
        <EventBadge />
        <UserMenu />
      </div>
    </div>
    <RadarTabs />
    <StaleBanner />
  </header>
);
