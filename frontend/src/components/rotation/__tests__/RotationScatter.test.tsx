import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RotationScatter } from '../RotationScatter';
import type { Theme } from '@/types/themes';

const mkTheme = (id: string, long: number, short: number, composite: number): Theme => ({
  id,
  name: id,
  us_etfs: ['X'],
  primary_us: 'X',
  tags: [],
  note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short, mid: 50, long, composite },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

// Recharts 在 jsdom 下 ResponsiveContainer 默认宽 0, ScatterChart 也不渲染 SVG (ResizeObserver 不可用);
// stub 两者以保证测试稳定
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

const renderWithRouter = (ui: React.ReactNode) =>
  render(<MemoryRouter>{ui}</MemoryRouter>);

describe('RotationScatter', () => {
  it('renders without crash given themes', () => {
    const themes = [
      mkTheme('a', 80, 80, 90),
      mkTheme('b', 30, 80, 60),
      mkTheme('c', 30, 30, 40),
      mkTheme('d', 80, 30, 50),
    ];
    const { container, getByTestId } = renderWithRouter(<RotationScatter themes={themes} />);
    expect(getByTestId('rc-container')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('renders empty without crash', () => {
    const { getByTestId } = renderWithRouter(<RotationScatter themes={[]} />);
    expect(getByTestId('rc-container')).toBeInTheDocument();
  });
});
