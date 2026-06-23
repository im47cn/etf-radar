// frontend/src/hooks/usePortfolioEventDetection.ts
import { useEffect, useRef } from 'react';
import { useEventsSnapshot } from '@/hooks/useEventsSnapshot';
import { useUserEvents } from '@/hooks/useUserEvents';
import { detectEvents, type HoldingForDiff } from '@/lib/portfolio/eventDiff';

/** localStorage key — 同日节流，避免每次 mount 重跑检测 */
const STORAGE_KEY = 'portfolio_last_detected_date';

interface Args {
  todayDate:     string | undefined;
  yesterdayDate: string | undefined;
  holdings:      HoldingForDiff[];
}

/**
 * 持仓事件检测触发器（spec §3.7）。
 *
 * 流程：访问 /portfolio → 拉 today + yesterday 快照 → detectEvents → upsert → 写 localStorage。
 *
 * 节流：localStorage(`portfolio_last_detected_date`) 同日不重跑，避免每次 mount 都打库。
 *   节流 key 仅用 date 不绑 user — 同设备多账号场景下检测一次即可，
 *   因为 user_events 由 UNIQUE 约束做最终 dedupe（即便重复 detect，库里也只有一份）。
 */
export function usePortfolioEventDetection({
  todayDate, yesterdayDate, holdings,
}: Args): void {
  const today     = useEventsSnapshot(todayDate);
  const yesterday = useEventsSnapshot(yesterdayDate);
  const { upsertEvents } = useUserEvents();

  // 防止 React Strict Mode 双 mount 时重复触发
  const firedRef = useRef(false);

  useEffect(() => {
    if (firedRef.current) return;

    // 前置守卫：日期、持仓、快照都就位才执行
    if (!todayDate || !yesterdayDate) return;
    if (holdings.length === 0) return;
    if (!today.snapshot || !yesterday.snapshot) return;

    // 同日节流：已标记则跳过
    const lastDetected = localStorage.getItem(STORAGE_KEY);
    if (lastDetected === todayDate) return;

    firedRef.current = true;

    // 检测事件，有事件才调 upsert
    const events = detectEvents(today.snapshot, yesterday.snapshot, holdings);
    if (events.length > 0) {
      // 静默 rejection 会让生产事件 upsert 失败无声; 至少落 console
      upsertEvents(events).catch(err => console.error('[event-detection] upsert 失败', err));
    }

    // 无论是否有事件，标记今日已检测，避免下次重跑
    localStorage.setItem(STORAGE_KEY, todayDate);
  }, [todayDate, yesterdayDate, today.snapshot, yesterday.snapshot, holdings, upsertEvents]);
}
