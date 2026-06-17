import { useCallback, useEffect, useRef, useState } from 'react';

export type PlaySpeed = 1 | 2 | 4;

const DURATIONS: Record<PlaySpeed, number> = { 1: 300, 2: 150, 4: 80 };
const PREFETCH_AHEAD = 5;

export interface UseTimelinePlayerOptions {
  dates: string[];
  currentDate: string | undefined;
  onAdvance: (next: string) => void;
  onPrefetchNeeded?: (dates: string[]) => void;
}

export interface UseTimelinePlayerResult {
  playing: boolean;
  speed: PlaySpeed;
  animationDuration: number;
  play: () => void;
  pause: () => void;
  stop: () => void;
  setSpeed: (s: PlaySpeed) => void;
}

export function useTimelinePlayer(opts: UseTimelinePlayerOptions): UseTimelinePlayerResult {
  const { dates, currentDate, onAdvance, onPrefetchNeeded } = opts;
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaySpeed>(1);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentRef = useRef(currentDate);
  useEffect(() => {
    currentRef.current = currentDate;
  }, [currentDate]);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const tick = useCallback(() => {
    if (dates.length === 0) return;
    const cur = currentRef.current;
    const idx = cur ? dates.indexOf(cur) : -1;
    if (idx === -1 || idx >= dates.length - 1) {
      clearTimer();
      setPlaying(false);
      return;
    }
    onAdvance(dates[idx + 1]);
  }, [dates, onAdvance, clearTimer]);

  const play = useCallback(() => {
    if (dates.length === 0) return;
    clearTimer();
    const cur = currentRef.current;
    const idx = cur ? dates.indexOf(cur) : -1;
    if (idx >= dates.length - 1) {
      onAdvance(dates[0]);
    }
    if (onPrefetchNeeded) {
      const baseIdx = idx >= dates.length - 1 ? 0 : idx;
      const ahead = dates.slice(baseIdx + 1, baseIdx + 1 + PREFETCH_AHEAD);
      if (ahead.length > 0) onPrefetchNeeded(ahead);
    }
    setPlaying(true);
    timerRef.current = setInterval(tick, DURATIONS[speed]);
  }, [dates, speed, tick, clearTimer, onAdvance, onPrefetchNeeded]);

  const pause = useCallback(() => {
    clearTimer();
    setPlaying(false);
  }, [clearTimer]);

  const stop = useCallback(() => {
    clearTimer();
    setPlaying(false);
    if (dates.length > 0) onAdvance(dates[dates.length - 1]);
  }, [dates, onAdvance, clearTimer]);

  useEffect(() => {
    if (!playing || dates.length === 0) return;
    clearTimer();
    timerRef.current = setInterval(tick, DURATIONS[speed]);
    return clearTimer;
  }, [speed, playing, dates, tick, clearTimer]);

  useEffect(() => clearTimer, [clearTimer]);

  return {
    playing,
    speed,
    animationDuration: DURATIONS[speed],
    play,
    pause,
    stop,
    setSpeed,
  };
}
