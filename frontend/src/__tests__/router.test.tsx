import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { SWRConfig } from 'swr';
import React from 'react';
import { RadarPage } from '@/pages/RadarPage';
import { RotationPage } from '@/pages/RotationPage';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="rc-container" style={{ width: 800, height: 500 }}>{children}</div>
    ),
    ScatterChart: ({ children }: { children: React.ReactNode }) => (
      <svg data-testid="scatter-chart">{children}</svg>
    ),
    Scatter: ({ children }: { children: React.ReactNode }) => <g>{children}</g>,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    ReferenceLine: () => null,
    ReferenceArea: () => null,
    Tooltip: () => null,
    Cell: () => null,
    LabelList: () => null,
  };
});

vi.mock('@/providers/dataContext', () => ({
  useDataContext: () => ({
    themes: {
      schema_version: '1.0', generated_at: '',
      themes: [{
        id: 't1', name: 'T1', us_etfs: ['X'], primary_us: 'X', tags: [], note: '',
        returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
        strength: { short: 50, mid: 50, long: 50, composite: 50 },
        rank: { short: 1, mid: 1, long: 1, composite: 1 },
      }],
    },
    etfs: { schema_version: '1.0', generated_at: '', etfs: [] },
    signals: {
      schema_version: '1.0', generated_at: '',
      summary: { short_count: 0, mid_count: 0, long_count: 0, composite_count: 0 },
      theme_signals: [],
      pair_signals: [],
    },
    meta: { schema_version: '1.0', generated_at: '', as_of: '', stale_minutes: 0 },
    isLoading: false, error: null,
  }),
}));

vi.mock('@/providers/uiStateContext', async () => {
  const actual = await vi.importActual<typeof import('@/providers/uiStateContext')>(
    '@/providers/uiStateContext',
  );
  return {
    ...actual,
    useUIState: () => ({
      state: {
        selectedThemeId: null,
        dimension: 'composite',
        signalFilter: 'all',
        searchQuery: '',
      },
      dispatch: vi.fn(),
    }),
  };
});

// Stub usePortfolioScores: 避免 useAuth/Supabase 依赖渗透到 router 测试
vi.mock('@/hooks/usePortfolioScores', () => ({
  usePortfolioScores: () => ({
    scores: [],
    loading: false,
    ownedThemeIds: new Set<string>(),
  }),
}));

// Mock useSnapshotsTimeline to return index-error state
vi.mock('@/hooks/useSnapshotsTimeline', () => ({
  useSnapshotsTimeline: () => ({
    index: undefined,
    currentDate: undefined,
    frame: undefined,
    setDate: vi.fn(),
    prefetch: vi.fn(),
    getCachedFrame: vi.fn(),
    snapshotsFrames: [],
    status: 'index-error',
    error: undefined,
  }),
}));

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <Routes>
          <Route path="/" element={<RadarPage />} />
          <Route path="/rotation" element={<RotationPage />} />
        </Routes>
      </SWRConfig>
    </MemoryRouter>,
  );

describe('Router integration', () => {
  it('renders RadarPage on /', () => {
    renderAt('/');
    expect(screen.queryByTestId('rc-container')).toBeNull();
  });

  it('renders RotationPage on /rotation', () => {
    renderAt('/rotation');
    expect(screen.getByTestId('rc-container')).toBeInTheDocument();
    expect(screen.getByText(/持续强势/)).toBeInTheDocument();
  });
});
