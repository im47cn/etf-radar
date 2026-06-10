import React, { createContext, useContext } from 'react';
import useSWR, { SWRConfig } from 'swr';
import type { z } from 'zod';
import { ThemesFileSchema, type ThemesFile } from '@/types/themes';
import { EtfsFileSchema, type EtfsFile } from '@/types/etfs';
import { SignalsFileSchema, type SignalsFile } from '@/types/signals';
import { MetaFileSchema, type MetaFile } from '@/types/meta';

const BASE = import.meta.env.BASE_URL;

/**
 * Fetch + zod 验证. 解析失败抛 ZodError, SWR 暴露给上层 error.
 */
const fetchAndParse = async <S extends z.ZodTypeAny>(
  url: string,
  schema: S,
): Promise<z.infer<S>> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`fetch ${url} ${r.status}`);
  const json = await r.json();
  return schema.parse(json);
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
    (url: string) => fetchAndParse(url, ThemesFileSchema),
    { refreshInterval: 300_000 },
  );
  const etfs = useSWR<EtfsFile>(
    `${BASE}data/latest/etfs.json`,
    (url: string) => fetchAndParse(url, EtfsFileSchema),
    { refreshInterval: 300_000 },
  );
  const signals = useSWR<SignalsFile>(
    `${BASE}data/latest/signals.json`,
    (url: string) => fetchAndParse(url, SignalsFileSchema),
    { refreshInterval: 300_000 },
  );
  const meta = useSWR<MetaFile>(
    `${BASE}data/latest/meta.json`,
    (url: string) => fetchAndParse(url, MetaFileSchema),
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
