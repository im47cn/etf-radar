import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { DataContext, type DataContextValue } from '@/providers/dataContext';
import { ThemeList } from '../index';
import type { ThemesFile } from '@/types/themes';

// Stub usePortfolioScores: 测试不依赖 Auth/Supabase, 空持仓即可
vi.mock('@/hooks/usePortfolioScores', () => ({
  usePortfolioScores: () => ({
    scores: [],
    loading: false,
    ownedThemeIds: new Set<string>(),
  }),
}));

const mkS = (n: number) => ({ short: n, mid: n, long: n, composite: n });

const themesFile: ThemesFile = {
  schema_version: '1.1',
  generated_at: '2026-06-20T00:00:00Z',
  themes: [
    {
      id: 'ai',
      name: 'AI',
      us_etfs: ['BOTZ'],
      primary_us: 'BOTZ',
      primary_cn: '159819',
      tags: [],
      note: '',
      returns: { r_1d: 1, r_5d: 2, r_20d: 3, r_60d: 4, r_120d: 5, r_ytd: 6 },
      strength: mkS(80),
      us_strength: mkS(90),
      cn_strength: mkS(50),
      rank: { short: 1, mid: 1, long: 1, composite: 1 },
    },
    {
      id: 'cn_liquor',
      name: '白酒',
      us_etfs: [],
      primary_us: null,
      primary_cn: '512690',
      tags: [],
      note: '',
      returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
      strength: mkS(60),
      us_strength: null,
      cn_strength: mkS(60),
      rank: { short: 2, mid: 2, long: 2, composite: 2 },
    },
  ],
};

const ctxValue: DataContextValue = {
  themes: themesFile,
  etfs: undefined,
  signals: undefined,
  meta: undefined,
  isLoading: false,
  error: null,
};

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <DataContext.Provider value={ctxValue}>
        <UIStateProvider>
          <ThemeList />
        </UIStateProvider>
      </DataContext.Provider>
    </MemoryRouter>,
  );

describe('ThemeList × MarketView 集成', () => {
  it('mv=us 隐藏 cn-only,头部 "美股主题强弱"', () => {
    renderAt('/?mv=us');
    expect(screen.getByText('美股主题强弱')).toBeInTheDocument();
    expect(screen.getByText('AI')).toBeInTheDocument();
    expect(screen.queryByText('白酒')).not.toBeInTheDocument();
  });

  it('mv=cn-all 同时展示 mapped 与 cn-only,头部 "A 股主题强弱"', () => {
    renderAt('/?mv=cn-all');
    expect(screen.getByText('A 股主题强弱')).toBeInTheDocument();
    expect(screen.getByText('AI')).toBeInTheDocument();
    expect(screen.getByText('白酒')).toBeInTheDocument();
  });

  it('mv=cn-all 排序按 cn_strength,mapped(50) 落后于 cn-only(60)', () => {
    renderAt('/?mv=cn-all');
    const rows = screen.getAllByRole('row');
    // rows[0] = thead, rows[1] = first data row
    const first = within(rows[1]);
    expect(first.getByText('白酒')).toBeInTheDocument();
  });
});
