import { AuthGate } from '@/components/portfolio/AuthGate';
import { MemberGate } from '@/components/membership/MemberGate';
import { WatchlistView } from '@/components/membership/WatchlistView';

export const WatchlistPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <AuthGate>
      <MemberGate>
        <WatchlistView />
      </MemberGate>
    </AuthGate>
  </div>
);
