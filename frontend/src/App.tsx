import { HashRouter, Routes, Route } from 'react-router-dom';
import { DataProvider } from '@/providers/DataProvider';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { Header } from '@/components/Header';
import { RadarPage } from '@/pages/RadarPage';
import { RotationPage } from '@/pages/RotationPage';

export default function App() {
  return (
    <DataProvider>
      <HashRouter>
        <UIStateProvider>
          <div className="min-h-screen bg-gray-50">
            <Header />
            <Routes>
              <Route path="/" element={<RadarPage />} />
              <Route path="/rotation" element={<RotationPage />} />
            </Routes>
          </div>
        </UIStateProvider>
      </HashRouter>
    </DataProvider>
  );
}
