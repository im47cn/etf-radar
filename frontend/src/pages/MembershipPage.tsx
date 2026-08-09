import { FeatureGate } from '@/components/gate/FeatureGate';
import { MembershipPanel } from '@/components/membership/MembershipPanel';

export const MembershipPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <FeatureGate copy="membership" required="auth">
      <MembershipPanel />
    </FeatureGate>
  </div>
);
