import { FilterBar } from '@/components/FilterBar';
import { ThemeList } from '@/components/ThemeList';
import { ThemeDetail } from '@/components/ThemeDetail';
import { CnEtfTable } from '@/components/CnEtfTable';

export const RadarPage = () => (
  <>
    <FilterBar />
    <main className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
      <ThemeList />
      <ThemeDetail />
    </main>
    <div className="px-4 pb-8">
      <CnEtfTable />
    </div>
  </>
);
