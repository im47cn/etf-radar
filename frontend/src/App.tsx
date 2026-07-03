import { HashRouter, Routes, Route } from 'react-router-dom';
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
                  <Routes>
                    <Route path="/"               element={<TemperaturePage />} />
                    <Route path="/rotation"       element={<RotationPage />} />
                    <Route path="/radar"          element={<RadarPage />} />
                    <Route path="/temperature"    element={<TemperaturePage />} />
                    <Route path="/portfolio"      element={<PortfolioPage />} />
                    <Route path="/auth/callback"  element={<AuthCallback />} />
                    <Route path="/theme/:id/stocks" element={<StocksPage />} />
                  </Routes>
                </div>
              </UIStateProvider>
            </EventsProvider>
          </HoldingsProvider>
        </AuthProvider>
      </HashRouter>
    </DataProvider>
  );
}
