import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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

export function useSnapshotsTimeline(): UseSnapshotsTimelineResult {
  const { data: index, error: indexError } = useSWR<SnapshotsIndex>(
    INDEX_URL,
    indexFetcher,
    { errorRetryInterval: 5000, revalidateOnFocus: false },
  );

  // cache 改 state (而非 ref): useMemo 直接依赖, 满足 react-hooks/refs 严格规则
  // (refs 不可在 render 期间读). put 通过 functional setState 保证不变性.
  const [cache, setCache] = useState<Map<string, SnapshotFrame>>(() => new Map());
  // overrideDate 优先于派生的 latestDate; 用户手动切日期时设置.
  const [overrideDate, setOverrideDate] = useState<string | undefined>();
  // errorDates: 拉取失败的日期集合. 在 fetchFrame 内更新, 不在 useEffect 内 — 满足
  // react-hooks/set-state-in-effect 规则.
  const [errorDates, setErrorDates] = useState<Set<string>>(() => new Set());
  // stableFrame: 最近一次成功拉取的帧, 作为 cache miss 时的兜底.
  // 契约 (见测试 "keeps previous frame on frame-error"): 当 setDate 目标日期拉取失败时,
  // frame 字段不应变 undefined, 而应保留上一次成功展示的帧引用.
  const [stableFrame, setStableFrame] = useState<SnapshotFrame | undefined>();
  const inflight = useRef<Set<string>>(new Set());

  // cacheReadRef 让异步回调 (fetchFrame) 读到最新 cache, 避免 useCallback
  // 依赖 cache 引发 fetchFrame 重建 → effects 级联. useEffect 内同步写, render 期不读 — 合规.
  const cacheReadRef = useRef(cache);
  useEffect(() => {
    cacheReadRef.current = cache;
  }, [cache]);

  // currentDateRef: 让 fetchFrame 判断 "当前拉取的日期是否就是用户正在查看的日期".
  // 仅在匹配时才更新 stableFrame, 避免被预取帧污染.
  const currentDateRef = useRef<string | undefined>(undefined);

  const pathByDate = useMemo(() => {
    if (!index) return new Map<string, string>();
    return new Map(index.snapshots.map((s) => [s.date, s.themes_path]));
  }, [index]);

  const fetchFrame = useCallback(
    async (date: string): Promise<SnapshotFrame | undefined> => {
      const cached = cacheReadRef.current.get(date);
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
    [pathByDate],
  );

  // currentDate 派生: overrideDate 优先, 否则取 index 最新.
  // 避免 useEffect 内 setState (react-hooks/set-state-in-effect).
  const currentDate =
    overrideDate ?? index?.snapshots[index.snapshots.length - 1]?.date;
  // frame 派生: 优先取当前日期的 cached 帧, miss 时 fallback 到 stableFrame.
  // 保证 frame-error 时 frame 不变 undefined (见 stableFrame 注释).
  const frame = (currentDate ? cache.get(currentDate) : undefined) ?? stableFrame;
  // frameError 派生: errorDates 包含 currentDate 时报错.
  const frameError =
    currentDate && errorDates.has(currentDate) ? currentDate : undefined;

  // currentDate 变化 / 启动 prefetch: 触发帧拉取. 错误状态由 fetchFrame 内部更新,
  // effect 自身不再 setState.
  //
  // eslint react-hooks/set-state-in-effect 误报: 规则跨函数追踪到 fetchFrame 内的
  // setCache / setErrorDates 调用并视为 effect setState. 实际上:
  // - effect deps 不含 cache / errorDates
  // - fetchFrame 内的 setState 仅改变 cache / errorDates → 不触发 effect 重跑
  // - 不存在 cascading rerender. 此 disable 是规则局限性而非代码问题.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!currentDate) return;
    currentDateRef.current = currentDate;
    fetchFrame(currentDate).catch(() => {
      /* errorDates 已在 fetchFrame 内更新, 此处 swallow 防 unhandled rejection */
    });
  }, [currentDate, fetchFrame]);

  useEffect(() => {
    if (!index) return;
    const recent = index.snapshots.slice(-PREFETCH_RECENT).map((s) => s.date);
    recent.forEach((d) => {
      fetchFrame(d).catch(() => {});
    });
  }, [index, fetchFrame]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const setDate = useCallback(
    (date: string) => {
      setOverrideDate(date);
      // frame 派生; 仅需触发 fetchFrame, 错误状态由其内部更新
      fetchFrame(date).catch(() => {});
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
    (date: string): SnapshotFrame | undefined => cache.get(date),
    [cache],
  );

  // Ordered list of all currently-cached frames (old → new) following index order.
  // 直接依赖 cache state — useMemo 重算正确触发, 不用 loadedRevision 桥接.
  const snapshotsFrames = useMemo<SnapshotFrame[]>(() => {
    if (!index) return [];
    const out: SnapshotFrame[] = [];
    for (const s of index.snapshots) {
      const f = cache.get(s.date);
      if (f) out.push(f);
    }
    return out;
  }, [index, cache]);

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
