import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { Theme } from '@/types/themes';
import { WatchlistPage } from '../WatchlistPage';

const mockUseDataContext = vi.fn();
vi.mock('@/providers/dataContext', () => ({
  useDataContext: () => mockUseDataContext(),
}));
// FeatureGate 直接透传 children, 绕过会员判断 (本测试聚焦添加区块渲染)
vi.mock('@/components/gate/FeatureGate', () => ({
  FeatureGate: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/membership/WatchlistView', () => ({
  WatchlistView: () => <div data-testid="watchlist-view" />,
}));
vi.mock('@/components/membership/AddWatchButton', () => ({
  AddWatchButton: ({ itemKey }: { itemKey: string }) => (
    <button data-testid={`add-${itemKey}`}>+</button>
  ),
}));
vi.mock('@/components/help/PageHelp', () => ({ PageHelp: () => null }));

const mkTheme = (id: string): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: [],
  primary_us: null,
  primary_cn: 'CN-ETF',
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short: 50, mid: 50, long: 50, composite: 50 },
  us_strength: null,
  cn_strength: { short: 50, mid: 50, long: 50, composite: 50 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

describe('WatchlistPage', () => {
  it('themes 有数据时渲染"添加主题到自选"区块 + 每主题 AddWatchButton', () => {
    mockUseDataContext.mockReturnValue({
      themes: { themes: [mkTheme('ai'), mkTheme('semi')] },
    });
    render(<WatchlistPage />);
    expect(screen.getByText('添加主题到自选')).toBeInTheDocument();
    expect(screen.getByTestId('add-ai')).toBeInTheDocument();
    expect(screen.getByTestId('add-semi')).toBeInTheDocument();
  });

  it('themes 为 undefined 时不渲染添加区块', () => {
    mockUseDataContext.mockReturnValue({ themes: undefined });
    render(<WatchlistPage />);
    expect(screen.queryByText('添加主题到自选')).not.toBeInTheDocument();
  });

  it('themes.themes 为空数组时不渲染添加区块', () => {
    mockUseDataContext.mockReturnValue({ themes: { themes: [] } });
    render(<WatchlistPage />);
    expect(screen.queryByText('添加主题到自选')).not.toBeInTheDocument();
  });
});
