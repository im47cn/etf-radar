import { FeatureGate } from '@/components/gate/FeatureGate';
import { HoldingsList } from '@/components/portfolio/HoldingsList';

export const PortfolioPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <FeatureGate copy="portfolio" required="auth">
      <HoldingsList />
    </FeatureGate>
  </div>
);
