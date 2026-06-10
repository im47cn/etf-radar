import React, { createContext, useContext } from 'react';
import useSWR, { SWRConfig } from 'swr';
import type { ThemesFile } from '@/types/themes';
import type { EtfsFile } from '@/types/etfs';
import type { SignalsFile } from '@/types/signals';
import type { MetaFile } from '@/types/meta';

const BASE = import.meta.env.BASE_URL;

const fetcher = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`fetch ${url} ${r.status}`);
  return r.json() as Promise<T>;
};

interface DataContextValue {
  themes?: ThemesFile;
  etfs?: EtfsFile;
  signals?: SignalsFile;
  meta?: MetaFile;
  isLoading: boolean;
  error: Error | null;
}

const DataContext = createContext<DataContextValue | null>(null);

export const DataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const themes = useSWR<ThemesFile>(
    `${BASE}data/latest/themes.json`,
    fetcher,
    { refreshInterval: 300_000 },
  );
  const etfs = useSWR<EtfsFile>(
    `${BASE}data/latest/etfs.json`,
    fetcher,
    { refreshInterval: 300_000 },
  );
  const signals = useSWR<SignalsFile>(
    `${BASE}data/latest/signals.json`,
    fetcher,
    { refreshInterval: 300_000 },
  );
  const meta = useSWR<MetaFile>(
    `${BASE}data/latest/meta.json`,
    fetcher,
    { refreshInterval: 60_000 },
  );

  const isLoading =
    themes.isLoading || etfs.isLoading || signals.isLoading || meta.isLoading;
  const error =
    (themes.error as Error | undefined) ||
    (etfs.error as Error | undefined) ||
    (signals.error as Error | undefined) ||
    (meta.error as Error | undefined) ||
    null;

  return (
    <SWRConfig value={{ revalidateOnFocus: false }}>
      <DataContext.Provider
        value={{
          themes: themes.data,
          etfs: etfs.data,
          signals: signals.data,
          meta: meta.data,
          isLoading,
          error,
        }}
      >
        {children}
      </DataContext.Provider>
    </SWRConfig>
  );
};

export const useDataContext = (): DataContextValue => {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useDataContext must be inside DataProvider');
  return ctx;
};
