import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStocksSpot } from '../useStocksSpot';

let fetchSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => { fetchSpy = vi.spyOn(globalThis, 'fetch'); });
afterEach(() => { fetchSpy.mockRestore(); });

describe('useStocksSpot', () => {
  it('returns spots map on success', async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({
      schema_version: '1.0',
      generated_at: '2026-06-23T07:30:00+00:00',
      stocks: {
        '002129': { name: 'TCL中环', close: 12.5, r_1d: 0.025 },
      },
    })));

    const { result } = renderHook(() => useStocksSpot());
    await waitFor(() => expect(result.current.spots).not.toBeNull());
    expect(result.current.spots?.['002129']?.close).toBe(12.5);
  });

  it('returns null on 404', async () => {
    fetchSpy.mockResolvedValue(new Response('', { status: 404 }));
    const { result } = renderHook(() => useStocksSpot());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.spots).toBeNull();
  });
});
