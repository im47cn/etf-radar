import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useStockOhlc } from '../useStockOhlc';
import type { StockOhlc } from '@/types/stockIndicators';

const mockOhlc: StockOhlc = {
  code: '600519',
  name: '贵州茅台',
  bars: [{ date: '2026-01-01', o: 100, h: 110, l: 95, c: 105, v: 1000 }],
} as StockOhlc;

describe('useStockOhlc', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('code=null 时返回 loading=false, data=null', async () => {
    const { result } = renderHook(() => useStockOhlc(null));
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('成功 fetch 返回数据', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => mockOhlc,
    } as Response);
    const { result } = renderHook(() => useStockOhlc('600519'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data?.code).toBe('600519');
    expect(result.current.error).toBeNull();
  });

  it('404 返回 null data 不报错', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => null,
    } as Response);
    const { result } = renderHook(() => useStockOhlc('404CODE'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('非 404 错误抛 Error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => null,
    } as Response);
    const { result } = renderHook(() => useStockOhlc('ERR500'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toContain('500');
  });

  it('网络错误设置 error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useStockOhlc('NETERR'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
