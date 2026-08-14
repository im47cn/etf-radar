import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/hooks/useSignalEvidence', () => ({ useSignalEvidence: vi.fn() }));
vi.mock('@/lib/subscription/useSubscription', () => ({ useSubscription: vi.fn() }));
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  };
});

import { useSignalEvidence } from '@/hooks/useSignalEvidence';
import { useSubscription } from '@/lib/subscription/useSubscription';
import { AuthContext } from '@/providers/authContext';
import { GridPage } from '@/pages/GridPage';

const mockUse = (overrides: Record<string, unknown> = {}) => ({
  data: {
    grid_fitness: {
      themes: [{ theme_id: 'a', name: '半导体', grid_score: 0.82, verdict: 'suitable', ann_vol: 0.3, hurst: 0.4 }],
      summary: { tested: 1, skipped: 0, suitable_count: 1, median_score: 0.82 },
      weights: { vol: 0.4, mean_reversion: 0.35, arch: 0.25 },
    },
  },
  error: undefined,
  isLoading: false,
  ...overrides,
});

const renderPage = (overrides: Record<string, unknown> = {}) => {
  vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
  vi.mocked(useSignalEvidence).mockReturnValue(mockUse(overrides) as never);
  render(
    <MemoryRouter>
      <AuthContext.Provider value={{ status: 'authenticated', user: { email: 'a@b.com' } } as never}>
        <GridPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
};

describe('GridPage', () => {
  it('渲染标题与 summary (data 分支)', () => {
    renderPage();
    expect(screen.getByText(/网格选标/)).toBeInTheDocument();
    expect(screen.queryByText(/单边趋势/)).toBeNull(); // 非趋势市无提示
  });

  it('过半主题触发趋势护栏时显示市场级趋势提示', () => {
    renderPage({ data: {
      grid_fitness: {
        themes: [
          { theme_id: 'a', name: '中概', grid_score: 0.8, verdict: 'marginal', trend_regime: 'down' },
          { theme_id: 'b', name: '煤炭', grid_score: 0.7, verdict: 'suitable', trend_regime: null },
          { theme_id: 'c', name: '券商', grid_score: 0.5, verdict: 'marginal', trend_regime: 'up' },
        ],
        summary: { tested: 3, skipped: 0, suitable_count: 1, median_score: 0.7 },
        weights: { vol: 0.4, mean_reversion: 0.35, arch: 0.25 },
      },
    } });
    expect(screen.getByText(/2\/3 个主题处于单边趋势/)).toBeInTheDocument();
    expect(screen.getByText(/网格机会稀缺/)).toBeInTheDocument();
  });

  it('加载中显示骨架 (loading 分支)', () => {
    renderPage({ isLoading: true, data: null });
    expect(screen.queryByText(/网格选标/)).toBeNull();
  });

  it('错误显示占位 (error 分支)', () => {
    renderPage({ error: new Error('x'), data: null });
    expect(screen.getByText(/暂无网格适配度数据/)).toBeInTheDocument();
  });
});
