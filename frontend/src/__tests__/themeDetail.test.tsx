import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// recharts mock：参考 evidenceCharts.test / router.test 模式
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  const Node = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  const Stub = () => null;
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
      <div data-testid="rc">{children}</div>
    ),
    RadialBarChart: Node,
    RadialBar: Node,
    PolarAngleAxis: Stub,
    BarChart: Node,
    Bar: Node,
    Cell: Stub,
    XAxis: Stub,
    YAxis: Stub,
    CartesianGrid: Stub,
    Tooltip: Stub,
    LabelList: Stub,
  };
});

import { PeriodReturns } from '@/components/ThemeDetail/PeriodReturns';
import { StrengthRing } from '@/components/ThemeDetail/StrengthRing';
import { TagPills } from '@/components/ThemeDetail/TagPills';
import { SignalNote } from '@/components/ThemeDetail/SignalNote';
import { StrengthBars } from '@/components/ThemeDetail/StrengthBars';

describe('PeriodReturns', () => {
  it('渲染所有 6 个周期标签', () => {
    const returns = {
      r_1d: 0.01, r_5d: -0.02, r_20d: 0.03, r_60d: null, r_120d: -0.01, r_ytd: 0.05,
    };
    render(<PeriodReturns returns={returns} />);
    expect(screen.getByText('1日')).toBeInTheDocument();
    expect(screen.getByText('5日')).toBeInTheDocument();
    expect(screen.getByText('20日')).toBeInTheDocument();
    expect(screen.getByText('60日')).toBeInTheDocument();
    expect(screen.getByText('120日')).toBeInTheDocument();
    expect(screen.getByText('年初至今')).toBeInTheDocument();
  });

  it('正值用蓝色，负值用红色', () => {
    render(<PeriodReturns returns={{ r_1d: 0.01, r_5d: -0.02, r_20d: null, r_60d: null, r_120d: null, r_ytd: null }} />);
    const cells = screen.getAllByText(/%/);
    expect(cells[0].className).toContain('text-blue');
    expect(cells[1].className).toContain('text-red');
  });

  it('null 值显示占位符', () => {
    render(<PeriodReturns returns={{ r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null }} />);
    const dashes = screen.getAllByText('—');
    expect(dashes).toHaveLength(6);
  });
});

describe('StrengthRing', () => {
  it('渲染数值和标签', () => {
    render(<StrengthRing value={75} label="综合" />);
    expect(screen.getByText('75')).toBeInTheDocument();
    expect(screen.getByText('综合')).toBeInTheDocument();
    expect(screen.getAllByTestId('rc').length).toBeGreaterThan(0);
  });
});

describe('TagPills', () => {
  it('渲染所有 tag', () => {
    render(<TagPills tags={['科技', '半导体', 'AI']} />);
    expect(screen.getByText('科技')).toBeInTheDocument();
    expect(screen.getByText('半导体')).toBeInTheDocument();
    expect(screen.getByText('AI')).toBeInTheDocument();
  });

  it('空数组不渲染任何 pill', () => {
    const { container } = render(<TagPills tags={[]} />);
    expect(container.querySelectorAll('span').length).toBe(0);
  });
});

describe('SignalNote', () => {
  it('signal=null 返回 null（不渲染）', () => {
    const { container } = render(<SignalNote signal={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('resonance 渲染共振说明', () => {
    render(<SignalNote signal="resonance" />);
    expect(screen.getByText('共振说明')).toBeInTheDocument();
    expect(screen.getByText(/两边在多个周期同向走强或走弱/)).toBeInTheDocument();
  });

  it('transmission 渲染传导说明', () => {
    render(<SignalNote signal="transmission" />);
    expect(screen.getByText('传导说明')).toBeInTheDocument();
  });

  it('transmission 显示无方向预测力提示 (回测 49%≈随机)', () => {
    render(<SignalNote signal="transmission" />);
    expect(screen.getByText(/无方向预测力/)).toBeInTheDocument();
  });

  it('divergence 渲染背离说明', () => {
    render(<SignalNote signal="divergence" />);
    expect(screen.getByText('背离说明')).toBeInTheDocument();
  });

  it('resonance + direction up 显示偏多与胜率提示', () => {
    render(<SignalNote signal="resonance" direction="up" />);
    expect(screen.getByText('偏多 ▲')).toBeInTheDocument();
    expect(screen.getByText(/数日内 A 股同向概率约 55%/)).toBeInTheDocument();
  });

  it('resonance 高置信档显示幅度分层标签', () => {
    render(<SignalNote signal="resonance" direction="up" directionTier="high" />);
    expect(screen.getByText('偏多 ▲（高置信）')).toBeInTheDocument();
    expect(screen.getByText(/\|动量\|≥1% 时数日内 A 股同向概率约 57%/)).toBeInTheDocument();
  });

  it('resonance 弱信号档灰显并提示随机性', () => {
    render(<SignalNote signal="resonance" direction="up" directionTier="low" />);
    expect(screen.getByText('偏多 ▲（弱信号）')).toBeInTheDocument();
    expect(screen.getByText(/同向概率≈48%（≈随机）/)).toBeInTheDocument();
  });

  it('resonance + direction down 显示偏空', () => {
    render(<SignalNote signal="resonance" direction="down" />);
    expect(screen.getByText('偏空 ▼')).toBeInTheDocument();
  });

  it('transmission 即使有 direction 也不显示方向标签 (仅 resonance 方向有意义)', () => {
    const { container } = render(<SignalNote signal="transmission" direction="up" />);
    expect(container.textContent).not.toContain('偏多');
  });
});

describe('StrengthBars', () => {
  it('渲染 4 个维度标签和数值', () => {
    const strength = { short: 30, mid: 60, long: 80, composite: 50 };
    render(<StrengthBars strength={strength} />);
    expect(screen.getByText('短期')).toBeInTheDocument();
    expect(screen.getByText('中期')).toBeInTheDocument();
    expect(screen.getByText('长期')).toBeInTheDocument();
    expect(screen.getByText('综合')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText('80')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
  });
});

// ---- ThemeDetail 整组件: direction_tier 透传 (变更行覆盖) ----
vi.mock('@/providers/dataContext', () => ({
  useDataContext: () => ({
    themes: {
      schema_version: '1.0', generated_at: '',
      themes: [{
        id: 't1', name: 'T1', us_etfs: ['X'], primary_us: 'X', primary_cn: '512480',
        tags: [], note: '',
        returns: { r_1d: 0.01, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
        strength: { short: 70, mid: 50, long: 50, composite: 55 },
        rank: { short: 1, mid: 1, long: 1, composite: 1 },
      }],
    },
    etfs: {
      schema_version: '1.0', generated_at: '',
      etfs: [{ code: '512480', market: 'CN', name: '半导体ETF',
        returns: { r_1d: 0.02, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
        strength: { short: 60, mid: 50, long: 50, composite: 55 } }],
    },
    signals: {
      schema_version: '1.0', generated_at: '',
      theme_signals: [{
        theme_id: 't1', signal: 'resonance', direction: 'up', direction_tier: 'high',
        trigger_cn_etf: '512480', votes: { short: 'resonance', mid: null, long: null },
        description: 'd',
      }],
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
      state: { selectedThemeId: 't1', dimension: 'composite', signalFilter: 'all', searchQuery: '' },
      dispatch: vi.fn(),
    }),
  };
});

describe('ThemeDetail (整组件)', () => {
  it('选中主题时把 direction_tier 透传给 SignalNote (高置信标注)', async () => {
    const { ThemeDetail } = await import('@/components/ThemeDetail');
    render(<ThemeDetail />);
    expect(screen.getByText('偏多 ▲（高置信）')).toBeInTheDocument();
  });
});
