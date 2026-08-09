import { FeatureGate } from '@/components/gate/FeatureGate';
import { WatchlistView } from '@/components/membership/WatchlistView';

export const WatchlistPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <FeatureGate copy="watchlist" required="member">
      <WatchlistView />
    </FeatureGate>
  </div>
);
