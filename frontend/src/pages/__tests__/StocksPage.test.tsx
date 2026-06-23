import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StocksPage } from '../StocksPage';
import type { Theme } from '@/types/themes';

// useDataContext lives in dataContext.ts (not DataProvider.tsx)
vi.mock('@/providers/dataContext', () => ({
  useDataContext: () => ({
    themes: { themes: mockThemes, schema_version: '1.0', generated_at: '' },
    isLoading: false,
    error: null,
  }),
}));

let mockThemes: Theme[] = [];

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/theme/:id/stocks" element={<StocksPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

let fetchSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => { fetchSpy = vi.spyOn(globalThis, 'fetch'); });
afterEach(() => { fetchSpy.mockRestore(); vi.clearAllMocks(); });

describe('StocksPage', () => {
  it('renders 404 when theme id not found', () => {
    mockThemes = [];
    renderAt('/theme/nonexistent/stocks');
    expect(screen.getByText(/未找到该主题/)).toBeInTheDocument();
  });

  it('renders empty state when theme has no primary_cn', () => {
    mockThemes = [
      { id: 'us_only', name: '纯美股主题', us_etfs: ['SOXX'], primary_us: 'SOXX',
        primary_cn: null, tags: [], note: '', returns: {} as unknown, strength: {} as unknown,
        us_strength: null, cn_strength: null, rank: {} as unknown } as unknown as Theme,
    ];
    renderAt('/theme/us_only/stocks');
    expect(screen.getByText(/美股个股数据.*Phase 2/)).toBeInTheDocument();
  });

  it('renders stock rows when holdings + spot are available', async () => {
    mockThemes = [
      { id: 'semi', name: '半导体', us_etfs: ['SOXX'], primary_us: 'SOXX',
        primary_cn: '512480', tags: [], note: '', returns: {} as unknown, strength: {} as unknown,
        us_strength: null, cn_strength: null, rank: {} as unknown } as unknown as Theme,
    ];
    fetchSpy.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('512480.json')) {
        return Promise.resolve(new Response(JSON.stringify({
          etf_code: '512480', etf_name: '半导体ETF',
          disclosure_date: '2026-03-31', fetched_at: '2026-06-23T00:00:00+00:00',
          top_holdings: [{ code: '002129', name: 'TCL中环', weight: 8.5 }],
        })));
      }
      if (url.includes('stocks_spot.json')) {
        return Promise.resolve(new Response(JSON.stringify({
          schema_version: '1.0', generated_at: '...',
          stocks: { '002129': { name: 'TCL中环', close: 12.5, r_1d: 0.025 } },
        })));
      }
      return Promise.resolve(new Response('', { status: 404 }));
    });
    renderAt('/theme/semi/stocks');
    await waitFor(() => expect(screen.getByText('TCL中环')).toBeInTheDocument());
    expect(screen.getByText('002129')).toBeInTheDocument();
  });
});
