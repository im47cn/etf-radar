import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RotationPage } from '../RotationPage';
import type { Theme } from '@/types/themes';

const mockUseDataContext = vi.fn();
vi.mock('@/providers/DataProvider', () => ({
  useDataContext: () => mockUseDataContext(),
}));

vi.mock('@/hooks/useSnapshotsTimeline', () => ({
  useSnapshotsTimeline: () => ({
    snapshotsFrames: [],
    status: 'ready',
  }),
}));

// Mock the overlay so the page test stays focused on wiring (not chart internals)
vi.mock('@/components/rotation/RotationTrailsOverlay', () => ({
  RotationTrailsOverlay: ({ themes }: { themes: Theme[] }) => (
    <div data-testid="trails-overlay" data-theme-count={themes.length}>
      <div>轨迹长度</div>
    </div>
  ),
}));

const mkTheme = (id: string): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: ['SOXX'],
  primary_us: 'SOXX',
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short: 80, mid: 70, long: 60, composite: 70 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

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
    mockUseDataContext.mockReturnValue({
      themes: undefined,
      isLoading: false,
      error: new Error('boom'),
    });
    renderPage();
    expect(screen.getByText(/数据加载失败/)).toBeInTheDocument();
  });

  it('renders empty alert when no themes', () => {
    mockUseDataContext.mockReturnValue({
      themes: { schema_version: '1.0', generated_at: '', themes: [] },
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText(/暂无主题数据/)).toBeInTheDocument();
  });

  it('renders RotationTrailsOverlay when data is ready', () => {
    mockUseDataContext.mockReturnValue({
      themes: { schema_version: '1.0', generated_at: '', themes: [mkTheme('ai')] },
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText(/主题轮动象限图/)).toBeInTheDocument();
    expect(screen.getByTestId('trails-overlay')).toBeInTheDocument();
    expect(screen.getByTestId('trails-overlay').getAttribute('data-theme-count')).toBe('1');
    expect(screen.getByText(/轨迹长度/)).toBeInTheDocument();
  });
});
