import { createContext, useContext } from 'react';
import type { ThemesFile } from '@/types/themes';
import type { EtfsFile } from '@/types/etfs';
import type { SignalsFile } from '@/types/signals';
import type { MetaFile } from '@/types/meta';

export interface DataContextValue {
  themes?: ThemesFile;
  etfs?: EtfsFile;
  signals?: SignalsFile;
  meta?: MetaFile;
  isLoading: boolean;
  error: Error | null;
}

export const DataContext = createContext<DataContextValue | null>(null);

export const useDataContext = (): DataContextValue => {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useDataContext must be inside DataProvider');
  return ctx;
};
