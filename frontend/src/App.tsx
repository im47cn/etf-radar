import { HashRouter, Routes, Route, useLocation } from 'react-router-dom';
import { useUIState } from '@/providers/uiStateContext';
import { DataProvider } from '@/providers/DataProvider';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { AuthProvider } from '@/providers/AuthProvider';
import { HoldingsProvider } from '@/providers/HoldingsProvider';
import { EventsProvider } from '@/providers/EventsProvider';
import { Header } from '@/components/Header';
import { RadarPage } from '@/pages/RadarPage';
import { RotationPage } from '@/pages/RotationPage';
import { PortfolioPage } from '@/pages/PortfolioPage';
import { AuthCallback } from '@/pages/AuthCallback';
import { StocksPage } from '@/pages/StocksPage';
import { TemperaturePage } from '@/pages/TemperaturePage';
import { MembershipPage } from '@/pages/MembershipPage';
import { WatchlistPage } from '@/pages/WatchlistPage';

// 路由 Tab 与市场视图切换共用一个 key，容器重挂载时触发 crossfade 淡入
const AnimatedRoutes = () => {
  const { pathname } = useLocation();
  const { state } = useUIState();
  return (
    <div key={`${pathname}-${state.marketView}`} className="animate-crossfade">
      <Routes>
        <Route path="/"               element={<TemperaturePage />} />
        <Route path="/rotation"       element={<RotationPage />} />
        <Route path="/radar"          element={<RadarPage />} />
        <Route path="/temperature"    element={<TemperaturePage />} />
        <Route path="/portfolio"      element={<PortfolioPage />} />
        <Route path="/membership"     element={<MembershipPage />} />
        <Route path="/watchlist"      element={<WatchlistPage />} />
        <Route path="/auth/callback"  element={<AuthCallback />} />
        <Route path="/theme/:id/stocks" element={<StocksPage />} />
      </Routes>
    </div>
  );
};

export default function App() {
  return (
    <DataProvider>
      <HashRouter>
        <AuthProvider>
          <HoldingsProvider>
            <EventsProvider>
              <UIStateProvider>
                <div className="min-h-screen bg-gray-50">
                  <Header />
                  <AnimatedRoutes />
                </div>
              </UIStateProvider>
            </EventsProvider>
          </HoldingsProvider>
        </AuthProvider>
      </HashRouter>
    </DataProvider>
  );
}
