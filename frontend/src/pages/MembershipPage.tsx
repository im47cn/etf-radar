import { AuthGate } from '@/components/portfolio/AuthGate';
import { MembershipPanel } from '@/components/membership/MembershipPanel';

export const MembershipPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <AuthGate>
      <MembershipPanel />
    </AuthGate>
  </div>
);
