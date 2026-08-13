import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/hooks/useSignalEvidence', () => ({
  useSignalEvidence: () => ({
    data: {
      schema_version: '1.0',
      as_of_date: '2026-08-07',
      sample: { start: '2021-08-09', end: '2026-08-07', n_days: 1212 },
      ic: {
        rolling: [{ date: '2021-11-09', ic_5: 0.02, ic_20: 0.03, ic_60: 0.05 }],
        by_horizon: [{ horizon: 20, ic: 0.054, t_stat: 7.9, n: 1192, ic_min: -0.5, ic_max: 0.7, recent_ic: 0.06 }],
      },
      arch: {
        themes: [{ theme_id: 'semi', name: '半导体', n: 1212, r2_lb_p: 0.0, is_arch: true, ret_lb_p: 0.02 }],
        summary: { arch_count: 26, tested: 30, expected_fp: 1.5 },
        representative_acf: { semi: [1.0, 0.18] },
        time_series: [
          { period: '2024-09', arch_ratio: 0.55, arch_count: 16, tested: 29 },
          { period: '2024-10', arch_ratio: 0.66, arch_count: 19, tested: 29 },
        ],
      },
      grid_fitness: {
        themes: [{ theme_id: 'semi', name: '半导体', n: 1212, ann_vol: 0.32, hurst: 0.42,
                  arch_neg_log10p: 5, pct_vol: 0.9, pct_mean_reversion: 0.7, pct_arch: 0.9,
                  grid_score: 0.82, verdict: 'suitable' }],
        summary: { tested: 29, skipped: 1, suitable_count: 12, median_score: 0.52 },
        weights: { vol: 0.4, mean_reversion: 0.35, arch: 0.25 },
      },
    },
    error: undefined,
    isLoading: false,
  }),
}));

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  const Node = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  const Stub = () => null;
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    LineChart: Node,
    BarChart: Node,
    Line: Stub,
    Bar: Node,
    Cell: Stub,
    ReferenceLine: Stub,
    Tooltip: Stub,
    XAxis: Stub,
    YAxis: Stub,
    CartesianGrid: Stub,
    LabelList: Stub,
  };
});

vi.mock('@/lib/subscription/useSubscription', () => ({
  useSubscription: vi.fn(),
}));

import { useSubscription } from '@/lib/subscription/useSubscription';
import { AuthContext } from '@/providers/authContext';
import { EvidencePage } from '@/pages/EvidencePage';

const renderPage = (
  authStatus: 'anonymous' | 'authenticated',
  subState: 'loading' | 'member' | 'non-member',
) => {
  vi.mocked(useSubscription).mockReturnValue({ state: subState } as never);
  render(
    <MemoryRouter>
      <AuthContext.Provider
        value={
          {
            status: authStatus,
            user: authStatus === 'authenticated' ? { email: 'a@b.com' } : null,
          } as never
        }
      >
        <EvidencePage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
};

describe('证据内容（member 态渲染）', () => {
  it('渲染标题 + 样本范围', () => {
    renderPage('authenticated', 'member');
    expect(screen.getByText('信号证据')).toBeInTheDocument();
    expect(screen.getByText(/2021-08-09 ~ 2026-08-07/)).toBeInTheDocument();
  });

  it('点 "使用说明" 打开综合弹层 (理论/方法/案例 三节)', async () => {
    const user = userEvent.setup();
    renderPage('authenticated', 'member');
    await user.click(screen.getByText('📖 使用说明'));
    expect(screen.getByText('理论基础')).toBeInTheDocument();
    expect(screen.getByText('使用方法（4 图怎么读）')).toBeInTheDocument();
    expect(screen.getByText('分析案例（5 年样本外实证）')).toBeInTheDocument();
  });

  it('每图 ? 按钮可打开各自弹层', async () => {
    const user = userEvent.setup();
    renderPage('authenticated', 'member');
    await user.click(screen.getByLabelText('Strength 月度 IC（多窗口滚动） 说明'));
    expect(screen.getByText('IC 多窗口时序 · 读法')).toBeInTheDocument();
  });
});

describe('EvidencePage 门控（会员功能）', () => {
  it('未登录 → hero 登录表单 + features，不渲染内容', () => {
    renderPage('anonymous', 'non-member');
    expect(screen.getByText(/5 年样本外 IC/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /发送登录链接/ })).toBeInTheDocument();
    expect(screen.queryByText('2021-08-09 ~ 2026-08-07')).toBeNull();
  });

  it('已登录非会员 → hero 升级卡（立即开通），不渲染内容', () => {
    renderPage('authenticated', 'non-member');
    expect(screen.getByText('立即开通会员').closest('a')).toHaveAttribute('href', '/membership');
    expect(screen.getByText(/5 年样本外 IC/)).toBeInTheDocument();
    expect(screen.queryByText('2021-08-09 ~ 2026-08-07')).toBeNull();
  });

  it('已登录会员 → 渲染证据内容', () => {
    renderPage('authenticated', 'member');
    expect(screen.getByText('信号证据')).toBeInTheDocument();
    expect(screen.getByText(/2021-08-09 ~ 2026-08-07/)).toBeInTheDocument();
  });
});
