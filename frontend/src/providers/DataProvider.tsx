import React, { createContext, useContext } from 'react';
import useSWR, { SWRConfig } from 'swr';
import type { z } from 'zod';
import { ThemesFileSchema, type ThemesFile } from '@/types/themes';
import { EtfsFileSchema, type EtfsFile } from '@/types/etfs';
import { SignalsFileSchema, type SignalsFile } from '@/types/signals';
import { MetaFileSchema, type MetaFile } from '@/types/meta';
import { LATEST_URLS } from '@/lib/dataUrls';

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

// SWRConfig 必须包在使用 useSWR 的组件外层, 否则全局配置不生效
export const DataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <SWRConfig value={{ revalidateOnFocus: false }}>
    <DataProviderInner>{children}</DataProviderInner>
  </SWRConfig>
);

const DataProviderInner: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const themes = useSWR<ThemesFile>(
    LATEST_URLS.themes,
    (url: string) => fetchAndParse(url, ThemesFileSchema),
    { refreshInterval: 300_000 },
  );
  const etfs = useSWR<EtfsFile>(
    LATEST_URLS.etfs,
    (url: string) => fetchAndParse(url, EtfsFileSchema),
    { refreshInterval: 300_000 },
  );
  const signals = useSWR<SignalsFile>(
    LATEST_URLS.signals,
    (url: string) => fetchAndParse(url, SignalsFileSchema),
    { refreshInterval: 300_000 },
  );
  const meta = useSWR<MetaFile>(
    LATEST_URLS.meta,
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
  );
};

export const useDataContext = (): DataContextValue => {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useDataContext must be inside DataProvider');
  return ctx;
};
