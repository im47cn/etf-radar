import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import {
  SnapshotsIndexSchema,
  SnapshotThemesFileSchema,
  type SnapshotsIndex,
  type SnapshotFrame,
} from '@/types/snapshots';
import { createLRU } from '@/lib/snapshotsCache';
import { LATEST_URLS, frameUrl } from '@/lib/dataUrls';

export type TimelineStatus = 'loading' | 'ready' | 'index-error' | 'frame-error';

export interface UseSnapshotsTimelineResult {
  index: SnapshotsIndex | undefined;
  currentDate: string | undefined;
  frame: SnapshotFrame | undefined;
  setDate: (date: string) => void;
  prefetch: (dates: string[]) => void;
  getCachedFrame: (date: string) => SnapshotFrame | undefined;
  snapshotsFrames: SnapshotFrame[];
  status: TimelineStatus;
  error: string | undefined;
}

// URL 构造已集中到 lib/dataUrls.ts, 配合契约测试杜绝 publicDir 平铺结构与
// fetch URL 前缀错配 (详见该模块顶部注释).
const INDEX_URL = LATEST_URLS.snapshotsIndex;
const CACHE_MAX = 20;
const PREFETCH_RECENT = 10;
const FRAME_MAX_RETRIES = 3;
const FRAME_RETRY_BASE_MS = 5000;

const indexFetcher = async (url: string): Promise<SnapshotsIndex> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`index ${res.status}`);
  return SnapshotsIndexSchema.parse(await res.json());
};

const frameFetcher = async (path: string, date: string): Promise<SnapshotFrame> => {
  const res = await fetch(frameUrl(path));
  if (!res.ok) throw new Error(`frame ${res.status}`);
  const parsed = SnapshotThemesFileSchema.parse(await res.json());
  return { date, themes: parsed.themes };
};

export function useSnapshotsTimeline(): UseSnapshotsTimelineResult {
  const { data: index, error: indexError } = useSWR<SnapshotsIndex>(
    INDEX_URL,
    indexFetcher,
    { errorRetryInterval: 5000, revalidateOnFocus: false },
  );

  const cacheRef = useRef(createLRU<SnapshotFrame>(CACHE_MAX));
  const [currentDate, setCurrentDate] = useState<string | undefined>();
  const [frame, setFrame] = useState<SnapshotFrame | undefined>();
  const [frameError, setFrameError] = useState<string | undefined>();
  // bump on every successful cache.put — triggers snapshotsFrames recompute
  const [loadedRevision, setLoadedRevision] = useState(0);
  const inflight = useRef<Set<string>>(new Set());

  const pathByDate = useMemo(() => {
    if (!index) return new Map<string, string>();
    return new Map(index.snapshots.map((s) => [s.date, s.themes_path]));
  }, [index]);

  const fetchFrame = useCallback(
    async (date: string): Promise<SnapshotFrame | undefined> => {
      const cached = cacheRef.current.get(date);
      if (cached) return cached;
      if (inflight.current.has(date)) return undefined;
      const path = pathByDate.get(date);
      if (!path) return undefined;

      inflight.current.add(date);
      let attempt = 0;
      let lastErr: unknown;
      while (attempt < FRAME_MAX_RETRIES) {
        try {
          const fetched = await frameFetcher(path, date);
          cacheRef.current.put(date, fetched);
          setLoadedRevision((v) => v + 1);
          inflight.current.delete(date);
          return fetched;
        } catch (e) {
          lastErr = e;
          attempt++;
          if (attempt < FRAME_MAX_RETRIES) {
            await new Promise((r) =>
              setTimeout(r, FRAME_RETRY_BASE_MS * Math.pow(2, attempt - 1)),
            );
          }
        }
      }
      inflight.current.delete(date);
      throw lastErr;
    },
    [pathByDate],
  );

  // 初始化: index 就绪后选 latest 并拉首帧
  useEffect(() => {
    if (!index || currentDate) return;
    const latest = index.snapshots[index.snapshots.length - 1].date;
    setCurrentDate(latest);
    fetchFrame(latest)
      .then((f) => {
        if (f) {
          setFrame(f);
          setFrameError(undefined);
        }
      })
      .catch(() => setFrameError(latest));
  }, [index, currentDate, fetchFrame]);

  // 启动 prefetch: 最近 PREFETCH_RECENT 帧
  useEffect(() => {
    if (!index) return;
    const recent = index.snapshots.slice(-PREFETCH_RECENT).map((s) => s.date);
    recent.forEach((d) => {
      fetchFrame(d).catch(() => {});
    });
  }, [index, fetchFrame]);

  const setDate = useCallback(
    (date: string) => {
      setCurrentDate(date);
      const cached = cacheRef.current.get(date);
      if (cached) {
        setFrame(cached);
        setFrameError(undefined);
        return;
      }
      fetchFrame(date)
        .then((f) => {
          if (f) {
            setFrame(f);
            setFrameError(undefined);
          }
        })
        .catch(() => setFrameError(date));
    },
    [fetchFrame],
  );

  const prefetch = useCallback(
    (dates: string[]) => {
      dates.forEach((d) => {
        fetchFrame(d).catch(() => {});
      });
    },
    [fetchFrame],
  );

  const getCachedFrame = useCallback(
    (date: string): SnapshotFrame | undefined => cacheRef.current.get(date),
    [],
  );

  // Ordered list of all currently-cached frames (old → new) following index order.
  // Recomputes when index changes or a new frame is put into cache.
  const snapshotsFrames = useMemo<SnapshotFrame[]>(() => {
    if (!index) return [];
    // Reference loadedRevision so useMemo re-runs after each cache.put
    void loadedRevision;
    const out: SnapshotFrame[] = [];
    for (const s of index.snapshots) {
      const f = cacheRef.current.get(s.date);
      if (f) out.push(f);
    }
    return out;
  }, [index, loadedRevision]);

  const status: TimelineStatus = indexError
    ? 'index-error'
    : !index
      ? 'loading'
      : frameError
        ? 'frame-error'
        : 'ready';

  return {
    index,
    currentDate,
    frame,
    setDate,
    prefetch,
    getCachedFrame,
    snapshotsFrames,
    status,
    error: frameError,
  };
}
