import { HashRouter, Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { useUIState } from '@/providers/uiStateContext';
import { DataProvider } from '@/providers/DataProvider';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { AuthProvider } from '@/providers/AuthProvider';
import { HoldingsProvider } from '@/providers/HoldingsProvider';
import { TradesProvider } from '@/providers/TradesProvider';
import { EventsProvider } from '@/providers/EventsProvider';
import { Header } from '@/components/Header';
import { RadarPage } from '@/pages/RadarPage';
import { RotationPage } from '@/pages/RotationPage';
import { AuthCallback } from '@/pages/AuthCallback';
import { StocksPage } from '@/pages/StocksPage';
import { TemperaturePage } from '@/pages/TemperaturePage';
import { EvidencePage } from '@/pages/EvidencePage';
import { GridPage } from '@/pages/GridPage';
import { MetalsPage } from '@/pages/MetalsPage';
import { TradingPage } from '@/pages/TradingPage';
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
        <Route path="/evidence"       element={<EvidencePage />} />
      <Route path="/grid"           element={<GridPage />} />
        <Route path="/metals"         element={<MetalsPage />} />
        <Route path="/trading"        element={<TradingPage />} />
        <Route path="/portfolio"      element={<Navigate to="/trading?tab=holdings" replace />} />
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
            <TradesProvider>
              <EventsProvider>
              <UIStateProvider>
                <div className="min-h-screen bg-gray-50">
                  <Header />
                  <AnimatedRoutes />
                </div>
              </UIStateProvider>
              </EventsProvider>
            </TradesProvider>
          </HoldingsProvider>
        </AuthProvider>
      </HashRouter>
    </DataProvider>
  );
}
