import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useIsMobile } from '../useIsMobile';

type MqlListener = (e: MediaQueryListEvent) => void;

interface FakeMql {
  matches: boolean;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
  _emit: (matches: boolean) => void;
}

const makeFakeMql = (initial: boolean): FakeMql => {
  let listener: MqlListener | null = null;
  const obj: FakeMql = {
    matches: initial,
    addEventListener: vi.fn((_type: string, l: MqlListener) => { listener = l; }),
    removeEventListener: vi.fn(() => { listener = null; }),
    _emit: (matches) => {
      obj.matches = matches;
      listener?.({ matches } as MediaQueryListEvent);
    },
  };
  return obj;
};

describe('useIsMobile', () => {
  let fakeMql: FakeMql;
  const originalMatchMedia = window.matchMedia;

  beforeEach(() => {
    fakeMql = makeFakeMql(false);
    (window as unknown as { matchMedia: typeof window.matchMedia }).matchMedia =
      vi.fn(() => fakeMql) as unknown as typeof window.matchMedia;
  });

  afterEach(() => {
    (window as unknown as { matchMedia: typeof window.matchMedia }).matchMedia = originalMatchMedia;
  });

  it('初始读 matchMedia 决定首值', () => {
    fakeMql.matches = true;
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it('订阅 change 事件并响应切换', () => {
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
    act(() => fakeMql._emit(true));
    expect(result.current).toBe(true);
    act(() => fakeMql._emit(false));
    expect(result.current).toBe(false);
  });

  it('unmount 时取消订阅', () => {
    const { unmount } = renderHook(() => useIsMobile());
    expect(fakeMql.addEventListener).toHaveBeenCalledTimes(1);
    unmount();
    expect(fakeMql.removeEventListener).toHaveBeenCalledTimes(1);
  });
});
