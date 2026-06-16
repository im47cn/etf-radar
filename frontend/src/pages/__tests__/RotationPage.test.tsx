import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RotationPage } from '../RotationPage';

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

const mockUseDataContext = vi.fn();
vi.mock('@/providers/DataProvider', () => ({
  useDataContext: () => mockUseDataContext(),
}));

const renderPage = () =>
  render(
    <MemoryRouter>
      <RotationPage />
    </MemoryRouter>,
  );

describe('RotationPage', () => {
  it('renders skeleton when loading', () => {
    mockUseDataContext.mockReturnValue({ themes: undefined, isLoading: true, error: null });
    renderPage();
    expect(screen.getByTestId('rotation-skeleton')).toBeInTheDocument();
  });

  it('renders error alert when error', () => {
    mockUseDataContext.mockReturnValue({ themes: undefined, isLoading: false, error: new Error('boom') });
    renderPage();
    expect(screen.getByText(/数据加载失败/)).toBeInTheDocument();
  });

  it('renders empty alert when no themes', () => {
    mockUseDataContext.mockReturnValue({
      themes: { schema_version: '1.0', generated_at: '', themes: [] },
      isLoading: false, error: null,
    });
    renderPage();
    expect(screen.getByText(/暂无主题数据/)).toBeInTheDocument();
  });

  it('renders scatter and legend when data ready', () => {
    mockUseDataContext.mockReturnValue({
      themes: {
        schema_version: '1.0', generated_at: '',
        themes: [{
          id: 't1', name: 'T1', us_etfs: ['X'], primary_us: 'X', tags: [], note: '',
          returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
          strength: { short: 80, mid: 50, long: 80, composite: 90 },
          rank: { short: 1, mid: 1, long: 1, composite: 1 },
        }],
      },
      isLoading: false, error: null,
    });
    renderPage();
    expect(screen.getByTestId('rc-container')).toBeInTheDocument();
    expect(screen.getByText(/持续强势/)).toBeInTheDocument();
  });
});
