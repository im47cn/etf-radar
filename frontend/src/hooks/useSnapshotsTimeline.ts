import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from 'react';
import useSWR from 'swr';
import {
  SnapshotsIndexSchema,
  SnapshotThemesFileSchema,
  type SnapshotsIndex,
  type SnapshotFrame,
} from '@/types/snapshots';
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
// CACHE_MAX 与 MAX_TRAIL_DAYS (30) 保持 ≥ 5 缓冲: 用户拖 slider 到 -30 天时,
// trail 需要 30 帧 + 当前帧 + 少量预取余量, LRU 不应在浏览过程中挤掉刚加载的帧.
const CACHE_MAX = 35;
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

/**
 * LRU eviction via insertion-order Map.
 * delete-then-set 把 key 移到 Map 末尾 (touch); 超过 MAX 时删头部 (最旧).
 */
const putWithLRU = (
  prev: Map<string, SnapshotFrame>,
  date: string,
  frame: SnapshotFrame,
): Map<string, SnapshotFrame> => {
  const next = new Map(prev);
  next.delete(date);
  next.set(date, frame);
  while (next.size > CACHE_MAX) {
    const oldest = next.keys().next().value;
    if (oldest === undefined) break;
    next.delete(oldest);
  }
  return next;
};

interface FrameCacheState {
  cache: Map<string, SnapshotFrame>;
  setCache: Dispatch<SetStateAction<Map<string, SnapshotFrame>>>;
  errorDates: Set<string>;
  setErrorDates: Dispatch<SetStateAction<Set<string>>>;
  stableFrame: SnapshotFrame | undefined;
  setStableFrame: Dispatch<SetStateAction<SnapshotFrame | undefined>>;
  inflight: MutableRefObject<Set<string>>;
  cacheReadRef: MutableRefObject<Map<string, SnapshotFrame>>;
}

// cache/errorDates/stableFrame 状态 + inflight/cacheReadRef 集中管理.
// cache 用 state (而非 ref): useMemo 直接依赖, 满足 react-hooks/refs 严格规则.
// cacheReadRef 让异步回调 (fetchFrame) 读到最新 cache, 避免 useCallback 依赖 cache
// 引发重建 → effects 级联. useEffect 内同步写, render 期不读 — 合规.
function useFrameCache(): FrameCacheState {
  const [cache, setCache] = useState<Map<string, SnapshotFrame>>(() => new Map());
  const [errorDates, setErrorDates] = useState<Set<string>>(() => new Set());
  const [stableFrame, setStableFrame] = useState<SnapshotFrame | undefined>();
  const inflight = useRef<Set<string>>(new Set());
  const cacheReadRef = useRef(cache);
  useEffect(() => {
    cacheReadRef.current = cache;
  }, [cache]);
  return {
    cache,
    setCache,
    errorDates,
    setErrorDates,
    stableFrame,
    setStableFrame,
    inflight,
    cacheReadRef,
  };
}

function usePathByDate(index: SnapshotsIndex | undefined): Map<string, string> {
  return useMemo(() => {
    if (!index) return new Map<string, string>();
    return new Map(index.snapshots.map((s) => [s.date, s.themes_path]));
  }, [index]);
}

// currentDateRef: 让 fetchFrame 判断 "当前拉取的日期是否就是用户正在查看的日期",
// 仅在匹配时才更新 stableFrame, 避免被预取帧污染. 重试逻辑: 指数退避最多 FRAME_MAX_RETRIES 次.
function useFrameFetcher(
  pathByDate: Map<string, string>,
  currentDateRef: MutableRefObject<string | undefined>,
  { cacheReadRef, inflight, setCache, setStableFrame, setErrorDates }: FrameCacheState,
) {
  return useCallback(
    async (date: string): Promise<SnapshotFrame | undefined> => {
      const cached = cacheReadRef.current.get(date);
      if (cached) {
        // 缓存命中也需提升 stableFrame, 否则用户切到已缓存日期 (跳过 fetch)
        // 再切到失败日期时, fallback 会回退到更早的帧而非"刚刚展示"的帧.
        // 仅当 date 是当前查看日期时才更新, 防止预取的 cache hit 污染 fallback.
        if (date === currentDateRef.current) {
          setStableFrame(cached);
        }
        return cached;
      }
      if (inflight.current.has(date)) return undefined;
      const path = pathByDate.get(date);
      if (!path) return undefined;

      inflight.current.add(date);
      let attempt = 0;
      let lastErr: unknown;
      while (attempt < FRAME_MAX_RETRIES) {
        try {
          const fetched = await frameFetcher(path, date);
          setCache((prev) => putWithLRU(prev, date, fetched));
          // 仅当拉取的日期是用户正在查看的日期时才更新 stableFrame.
          // 预取的非当前帧不应污染 fallback (否则切到失败日期时 fallback 会指向预取的帧而非
          // 用户上次实际查看的帧).
          if (date === currentDateRef.current) {
            setStableFrame(fetched);
          }
          // 拉取成功 → 清掉历史失败标记 (若有)
          setErrorDates((prev) => {
            if (!prev.has(date)) return prev;
            const next = new Set(prev);
            next.delete(date);
            return next;
          });
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
      setErrorDates((prev) => {
        if (prev.has(date)) return prev;
        const next = new Set(prev);
        next.add(date);
        return next;
      });
      throw lastErr;
    },
    [
      pathByDate,
      currentDateRef,
      cacheReadRef,
      inflight,
      setCache,
      setStableFrame,
      setErrorDates,
    ],
  );
}

// currentDate 变化 / 启动 prefetch: 触发帧拉取. 错误状态由 fetchFrame 内部更新,
// effect 自身不再 setState (cache/errorDates 写入封装在异步回调里, 与 effect 解耦).
function useTimelineFetchEffects(
  currentDate: string | undefined,
  index: SnapshotsIndex | undefined,
  fetchFrame: (date: string) => Promise<SnapshotFrame | undefined>,
  currentDateRef: MutableRefObject<string | undefined>,
) {
  useEffect(() => {
    if (!currentDate) return;
    currentDateRef.current = currentDate;
    fetchFrame(currentDate).catch(() => {
      /* errorDates 已在 fetchFrame 内更新, 此处 swallow 防 unhandled rejection */
    });
  }, [currentDate, fetchFrame, currentDateRef]);

  useEffect(() => {
    if (!index) return;
    const recent = index.snapshots.slice(-PREFETCH_RECENT).map((s) => s.date);
    recent.forEach((d) => {
      fetchFrame(d).catch(() => {});
    });
  }, [index, fetchFrame]);
}

function useTimelineActions(
  fetchFrame: (date: string) => Promise<SnapshotFrame | undefined>,
  cache: Map<string, SnapshotFrame>,
  currentDateRef: MutableRefObject<string | undefined>,
  setOverrideDate: Dispatch<SetStateAction<string | undefined>>,
) {
  const setDate = useCallback(
    (date: string) => {
      // 同步更新 currentDateRef, 防止 fetchFrame 在 useEffect rerender 之前
      // 用旧 ref 跳过 stableFrame 更新 (cache hit 同步路径会立刻判读 ref).
      currentDateRef.current = date;
      setOverrideDate(date);
      fetchFrame(date).catch(() => {});
    },
    [fetchFrame, currentDateRef, setOverrideDate],
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
    (date: string): SnapshotFrame | undefined => cache.get(date),
    [cache],
  );

  return { setDate, prefetch, getCachedFrame };
}

// Ordered list of all currently-cached frames (old → new) following index order.
// 直接依赖 cache state — useMemo 重算正确触发, 不用 loadedRevision 桥接.
function useSnapshotsFrames(
  index: SnapshotsIndex | undefined,
  cache: Map<string, SnapshotFrame>,
): SnapshotFrame[] {
  return useMemo<SnapshotFrame[]>(() => {
    if (!index) return [];
    const out: SnapshotFrame[] = [];
    for (const s of index.snapshots) {
      const f = cache.get(s.date);
      if (f) out.push(f);
    }
    return out;
  }, [index, cache]);
}

function computeStatus(
  indexError: unknown,
  index: SnapshotsIndex | undefined,
  frameError: string | undefined,
): TimelineStatus {
  if (indexError) return 'index-error';
  if (!index) return 'loading';
  if (frameError) return 'frame-error';
  return 'ready';
}

export function useSnapshotsTimeline(): UseSnapshotsTimelineResult {
  const { data: index, error: indexError } = useSWR<SnapshotsIndex>(
    INDEX_URL,
    indexFetcher,
    { errorRetryInterval: 5000, revalidateOnFocus: false },
  );

  // overrideDate 优先于派生的 latestDate; 用户手动切日期时设置.
  const [overrideDate, setOverrideDate] = useState<string | undefined>();
  const currentDateRef = useRef<string | undefined>(undefined);
  const frameCache = useFrameCache();
  const pathByDate = usePathByDate(index);
  const fetchFrame = useFrameFetcher(pathByDate, currentDateRef, frameCache);

  // currentDate 派生: overrideDate 优先, 否则取 index 最新.
  // 避免 useEffect 内 setState (react-hooks/set-state-in-effect).
  const currentDate =
    overrideDate ?? index?.snapshots[index.snapshots.length - 1]?.date;
  // frame 派生: 优先取当前日期的 cached 帧, miss 时 fallback 到 stableFrame.
  // 保证 frame-error 时 frame 不变 undefined (见 stableFrame 注释).
  const frame =
    (currentDate ? frameCache.cache.get(currentDate) : undefined) ?? frameCache.stableFrame;
  // frameError 派生: errorDates 包含 currentDate 时报错.
  const frameError =
    currentDate && frameCache.errorDates.has(currentDate) ? currentDate : undefined;

  useTimelineFetchEffects(currentDate, index, fetchFrame, currentDateRef);
  const { setDate, prefetch, getCachedFrame } = useTimelineActions(
    fetchFrame,
    frameCache.cache,
    currentDateRef,
    setOverrideDate,
  );
  const snapshotsFrames = useSnapshotsFrames(index, frameCache.cache);
  const status = computeStatus(indexError, index, frameError);

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
