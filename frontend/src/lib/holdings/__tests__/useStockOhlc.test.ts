import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStockOhlc } from '../useStockOhlc';

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
});
afterEach(() => {
  fetchSpy.mockRestore();
  vi.clearAllMocks();
});

describe('useStockOhlc', () => {
  it('does not fetch when code is null', () => {
    renderHook(() => useStockOhlc(null));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('fetches OHLC for given code', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          code: '002129',
          name: 'TCL中环',
          generated_at: '2026-06-25T00:00:00+00:00',
          bars: [{ date: '2026-04-01', o: 12.3, h: 12.6, l: 12.2, c: 12.5, v: 100 }],
        }),
      ),
    );
    const { result } = renderHook(() => useStockOhlc('002129'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data?.bars).toHaveLength(1);
  });
});
