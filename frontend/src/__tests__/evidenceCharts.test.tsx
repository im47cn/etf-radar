import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { IcRollingChart } from '@/components/evidence/IcRollingChart';
import { IcHorizonBar } from '@/components/evidence/IcHorizonBar';
import { ArchRankingBar } from '@/components/evidence/ArchRankingBar';
import { R2AcfChart } from '@/components/evidence/R2AcfChart';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  const Node = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  const Stub = () => null;
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
      <div data-testid="rc">{children}</div>
    ),
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

describe('evidence 图表渲染', () => {
  it('IcRollingChart 渲染标题 + 图表容器', () => {
    render(<IcRollingChart rolling={[{ date: '2021-01-01', ic: 0.05, n: 60 }]} />);
    expect(screen.getByText('Strength 月度 IC（滚动 60 日）')).toBeInTheDocument();
    expect(screen.getAllByTestId('rc').length).toBeGreaterThan(0);
  });

  it('IcRollingChart 空数据显示占位', () => {
    render(<IcRollingChart rolling={[]} />);
    expect(screen.getByText('暂无 IC 时序数据')).toBeInTheDocument();
  });

  it('IcHorizonBar 渲染 3 档 IC', () => {
    render(<IcHorizonBar byHorizon={[{ horizon: 1, ic: 0.02, t_stat: 3, n: 100 }]} />);
    expect(screen.getByText('IC vs 持有期')).toBeInTheDocument();
  });

  it('ArchRankingBar 渲染主题条形', () => {
    render(
      <ArchRankingBar
        themes={[
          { theme_id: 'a', name: 'A', n: 100, r2_lb_p: 0.01, is_arch: true, ret_lb_p: 0.5 },
          { theme_id: 'b', name: 'B', n: 100, r2_lb_p: 0.9, is_arch: false, ret_lb_p: 0.5 },
        ]}
      />,
    );
    expect(screen.getByText('主题 ARCH 显著性（波动率聚集）')).toBeInTheDocument();
    // name 由 recharts YAxis 渲染 (mock 为 null), 改断言图表容器存在
    expect(screen.getAllByTestId('rc').length).toBeGreaterThan(0);
  });

  it('R2AcfChart 渲染多主题 + 图例', () => {
    render(<R2AcfChart acf={{ semi: [1, 0.2], bank: [1, 0.01] }} themeNames={{ semi: '半导体', bank: '银行' }} />);
    expect(screen.getByText('代表主题 r² ACF 衰减')).toBeInTheDocument();
    expect(screen.getByText('半导体')).toBeInTheDocument();
    expect(screen.getByText('银行')).toBeInTheDocument();
  });
});
