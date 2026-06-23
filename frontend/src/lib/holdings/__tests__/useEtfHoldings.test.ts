import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useEtfHoldings } from '../useEtfHoldings';
import type { EtfHoldingsSnapshot } from '@/types/holdings';

const mkSnap = (code: string): EtfHoldingsSnapshot => ({
  etf_code: code,
  etf_name: `${code}-name`,
  disclosure_date: '2026-03-31',
  fetched_at: '2026-06-23T00:00:00+00:00',
  top_holdings: [{ code: '002129', name: 'TCL中环', weight: 8.5 }],
});

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
});
afterEach(() => {
  fetchSpy.mockRestore();
});

describe('useEtfHoldings', () => {
  it('fetches all ETF snapshots in parallel', async () => {
    fetchSpy.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      const code = url.match(/holdings\/(\d+)\.json/)?.[1] ?? '';
      return Promise.resolve(new Response(JSON.stringify(mkSnap(code))));
    });

    const { result } = renderHook(() => useEtfHoldings(['512480', '159870']));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data.map(s => s.etf_code).sort()).toEqual(['159870', '512480']);
  });

  it('returns partial results when one ETF 404s', async () => {
    fetchSpy.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('512480')) {
        return Promise.resolve(new Response('', { status: 404 }));
      }
      return Promise.resolve(new Response(JSON.stringify(mkSnap('159870'))));
    });

    const { result } = renderHook(() => useEtfHoldings(['512480', '159870']));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data[0].etf_code).toBe('159870');
    expect(result.current.error).toBeNull();
  });

  it('handles empty input', async () => {
    const { result } = renderHook(() => useEtfHoldings([]));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual([]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
