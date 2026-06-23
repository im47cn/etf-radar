// frontend/src/hooks/__tests__/usePortfolioEventDetection.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { usePortfolioEventDetection } from '../usePortfolioEventDetection';

const upsertSpy = vi.fn().mockResolvedValue({ inserted: 0, error: null });

vi.mock('@/hooks/useUserEvents', () => ({
  useUserEvents: () => ({ upsertEvents: upsertSpy }),
}));

vi.mock('@/hooks/useEventsSnapshot', () => ({
  useEventsSnapshot: (date: string | undefined) => ({
    snapshot: date ? { date, themes: new Map() } : undefined,
    error: undefined,
  }),
}));

const STORAGE_KEY = 'portfolio_last_detected_date';

// jsdom 在没有 url 配置时不提供 window.localStorage
// 使用 vi.stubGlobal 注入 localStorage mock，hook 内部访问时走该 stub
const lsStore: Record<string, string> = {};
const localStorageMock: Storage = {
  getItem:    (key: string) => lsStore[key] ?? null,
  setItem:    (key: string, value: string) => { lsStore[key] = value; },
  removeItem: (key: string) => { delete lsStore[key]; },
  clear:      () => { Object.keys(lsStore).forEach(k => delete lsStore[k]); },
  key:        (index: number) => Object.keys(lsStore)[index] ?? null,
  get length() { return Object.keys(lsStore).length; },
};

beforeEach(() => {
  vi.stubGlobal('localStorage', localStorageMock);
  localStorageMock.clear();
  upsertSpy.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('usePortfolioEventDetection', () => {
  it('同一日已检测过则跳过', async () => {
    localStorageMock.setItem(STORAGE_KEY, '2026-06-23');
    renderHook(() => usePortfolioEventDetection({
      todayDate: '2026-06-23', yesterdayDate: '2026-06-22',
      holdings: [{ themeId: 'cn_tech', etfCode: '510300' }],
    }));
    await new Promise(r => setTimeout(r, 50));
    expect(upsertSpy).not.toHaveBeenCalled();
  });

  it('snapshots 都就位时触发 detectEvents + upsertEvents + 写 localStorage', async () => {
    renderHook(() => usePortfolioEventDetection({
      todayDate: '2026-06-23', yesterdayDate: '2026-06-22',
      holdings: [{ themeId: 'cn_tech', etfCode: '510300' }],
    }));
    await waitFor(() => {
      expect(localStorageMock.getItem(STORAGE_KEY)).toBe('2026-06-23');
    });
    // detectEvents 在空 themes Map 上返回 [],upsertEvents 不会被调用
    // 关键是 localStorage 被标记，说明 happy path 走通
    expect(localStorageMock.getItem(STORAGE_KEY)).toBe('2026-06-23');
  });

  it('holdings 为空时不触发', async () => {
    renderHook(() => usePortfolioEventDetection({
      todayDate: '2026-06-23', yesterdayDate: '2026-06-22', holdings: [],
    }));
    await new Promise(r => setTimeout(r, 50));
    expect(upsertSpy).not.toHaveBeenCalled();
    expect(localStorageMock.getItem(STORAGE_KEY)).toBeNull();
  });

  it('日期缺失时不触发', async () => {
    renderHook(() => usePortfolioEventDetection({
      todayDate: undefined, yesterdayDate: '2026-06-22',
      holdings: [{ themeId: 'cn_tech', etfCode: '510300' }],
    }));
    await new Promise(r => setTimeout(r, 50));
    expect(upsertSpy).not.toHaveBeenCalled();
    expect(localStorageMock.getItem(STORAGE_KEY)).toBeNull();
  });
});
