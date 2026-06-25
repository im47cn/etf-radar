import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStockIndicators } from '../useStockIndicators';

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
});
afterEach(() => {
  fetchSpy.mockRestore();
  vi.clearAllMocks();
});

describe('useStockIndicators', () => {
  it('returns indicators map on success', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          schema_version: '1.0',
          generated_at: '2026-06-25T00:00:00+00:00',
          stocks: {
            '002129': {
              name: 'TCL中环',
              strength_60d: 87,
              strength_20d: 91,
              rsi_14: 62.3,
              vol_ratio: 1.85,
              leader: '⭐⭐',
            },
          },
        }),
      ),
    );
    const { result } = renderHook(() => useStockIndicators());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.get('002129')?.strength_60d).toBe(87);
  });

  it('returns empty map on 404', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('', { status: 404 }));
    const { result } = renderHook(() => useStockIndicators());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.size).toBe(0);
    expect(result.current.error).toBeNull();
  });
});
