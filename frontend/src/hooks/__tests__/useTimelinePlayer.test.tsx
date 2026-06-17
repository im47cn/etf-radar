import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTimelinePlayer } from '../useTimelinePlayer';

const dates = ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04'];

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('useTimelinePlayer', () => {
  it('advances onAdvance every animationDuration ms while playing', () => {
    const onAdvance = vi.fn();
    const { result } = renderHook(() =>
      useTimelinePlayer({ dates, currentDate: '2026-01-01', onAdvance }),
    );
    act(() => result.current.play());
    expect(result.current.playing).toBe(true);
    act(() => vi.advanceTimersByTime(300));
    expect(onAdvance).toHaveBeenCalledWith('2026-01-02');
  });

  it('auto-pauses at end of timeline', () => {
    const onAdvance = vi.fn();
    const { result, rerender } = renderHook(
      ({ currentDate }: { currentDate: string }) =>
        useTimelinePlayer({ dates, currentDate, onAdvance }),
      { initialProps: { currentDate: '2026-01-03' } },
    );
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(300));
    expect(onAdvance).toHaveBeenLastCalledWith('2026-01-04');
    rerender({ currentDate: '2026-01-04' });
    act(() => vi.advanceTimersByTime(300));
    expect(result.current.playing).toBe(false);
  });

  it('play() at end resets to first frame', () => {
    const onAdvance = vi.fn();
    const { result } = renderHook(() =>
      useTimelinePlayer({ dates, currentDate: '2026-01-04', onAdvance }),
    );
    act(() => result.current.play());
    expect(onAdvance).toHaveBeenCalledWith('2026-01-01');
  });

  it('setSpeed updates animationDuration and tick interval', () => {
    const onAdvance = vi.fn();
    const { result } = renderHook(() =>
      useTimelinePlayer({ dates, currentDate: '2026-01-01', onAdvance }),
    );
    act(() => result.current.setSpeed(4));
    expect(result.current.animationDuration).toBe(80);
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(80));
    expect(onAdvance).toHaveBeenCalledWith('2026-01-02');
  });

  it('stop() resets to last date and pauses', () => {
    const onAdvance = vi.fn();
    const { result } = renderHook(() =>
      useTimelinePlayer({ dates, currentDate: '2026-01-02', onAdvance }),
    );
    act(() => result.current.play());
    act(() => result.current.stop());
    expect(result.current.playing).toBe(false);
    expect(onAdvance).toHaveBeenLastCalledWith('2026-01-04');
  });

  it('empty dates: play() is a no-op', () => {
    const onAdvance = vi.fn();
    const { result } = renderHook(() =>
      useTimelinePlayer({ dates: [], currentDate: undefined, onAdvance }),
    );
    act(() => result.current.play());
    expect(result.current.playing).toBe(false);
    expect(onAdvance).not.toHaveBeenCalled();
  });
});
