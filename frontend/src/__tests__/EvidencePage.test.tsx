import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { EvidencePage } from '@/pages/EvidencePage';

vi.mock('@/hooks/useSignalEvidence', () => ({
  useSignalEvidence: () => ({
    data: {
      schema_version: '1.0',
      as_of_date: '2026-08-07',
      sample: { start: '2021-08-09', end: '2026-08-07', n_days: 1212 },
      ic: {
        rolling: [{ date: '2021-11-09', ic: 0.05, n: 60 }],
        by_horizon: [{ horizon: 20, ic: 0.054, t_stat: 7.9, n: 1192 }],
      },
      arch: {
        themes: [{ theme_id: 'semi', name: '半导体', n: 1212, r2_lb_p: 0.0, is_arch: true, ret_lb_p: 0.02 }],
        summary: { arch_count: 26, tested: 30, expected_fp: 1.5 },
        representative_acf: { semi: [1.0, 0.18] },
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

describe('EvidencePage', () => {
  it('渲染标题 + 样本范围', () => {
    render(<EvidencePage />);
    expect(screen.getByText('信号证据')).toBeInTheDocument();
    expect(screen.getByText(/2021-08-09 ~ 2026-08-07/)).toBeInTheDocument();
  });

  it('点 "使用说明" 打开综合弹层 (理论/方法/案例 三节)', async () => {
    const user = userEvent.setup();
    render(<EvidencePage />);
    await user.click(screen.getByText('📖 使用说明'));
    expect(screen.getByText('理论基础')).toBeInTheDocument();
    expect(screen.getByText('使用方法（4 图怎么读）')).toBeInTheDocument();
    expect(screen.getByText('分析案例（5 年样本外实证）')).toBeInTheDocument();
  });

  it('每图 ? 按钮可打开各自弹层', async () => {
    const user = userEvent.setup();
    render(<EvidencePage />);
    await user.click(screen.getByLabelText('Strength 月度 IC（滚动 60 日） 说明'));
    expect(screen.getByText('IC 滚动时序 · 读法')).toBeInTheDocument();
  });
});
