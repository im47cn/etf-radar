import { DataProvider } from '@/providers/DataProvider';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { Header } from '@/components/Header';
import { FilterBar } from '@/components/FilterBar';
import { ThemeList } from '@/components/ThemeList';
import { ThemeDetail } from '@/components/ThemeDetail';
import { CnEtfTable } from '@/components/CnEtfTable';

export default function App() {
  return (
    <DataProvider>
      <UIStateProvider>
        <div className="min-h-screen bg-gray-50">
          <Header />
          <FilterBar />
          <main className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ThemeList />
            <ThemeDetail />
          </main>
          <div className="px-4 pb-8">
            <CnEtfTable />
          </div>
        </div>
      </UIStateProvider>
    </DataProvider>
  );
}
