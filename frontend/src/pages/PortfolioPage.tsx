import { AuthGate } from '@/components/portfolio/AuthGate';
import { HoldingsList } from '@/components/portfolio/HoldingsList';

export const PortfolioPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <AuthGate>
      <HoldingsList />
    </AuthGate>
  </div>
);
