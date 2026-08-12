import { render, fireEvent, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { ReactNode } from 'react';
import { IndexCompareChart } from '../IndexCompareChart';
import type { MarketPoint } from '@/types/marketTemperature';
import type { IndexSeriesEntry } from '@/types/indexSeries';

// 图例已改为自渲染 (不依赖 recharts payload), mock 仅用于规避 jsdom 下 SVG/ResizeObserver.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => (
      <div data-testid="rc-container">{children}</div>
    ),
    ComposedChart: ({ children }: { children: ReactNode }) => (
      <div data-testid="composed">{children}</div>
    ),
    Line: ({ dataKey, hide }: { dataKey?: string | number; hide?: boolean }) => (
      <div data-testid={`line-${dataKey}`} data-hide={hide ? 'true' : 'false'} />
    ),
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
  };
});

const market: MarketPoint[] = [
  { date: '2026-01-01', rate: 50 },
  { date: '2026-01-02', rate: 55 },
];
const indices: IndexSeriesEntry[] = [
  { code: '000001', name: '上证指数', series: [3000, 3010] },
  { code: '399001', name: '深证成指', series: [9500, 9550] },
  { code: '000300', name: '沪深300', series: [4000, 4010] },
];

describe('IndexCompareChart', () => {
  it('market 为空时降级显示空态', () => {
    render(<IndexCompareChart market={[]} indices={indices} />);
    expect(screen.getByText('暂无指数对比数据')).toBeTruthy();
  });

  it('正常渲染图表容器与自渲染图例项', () => {
    render(<IndexCompareChart market={market} indices={indices} />);
    expect(screen.getByTestId('rc-container')).toBeTruthy();
    // 宽度项 + 3 指数项均出现在自渲染图例
    expect(screen.getByText('宽度站上率')).toBeTruthy();
    expect(screen.getByText('上证指数')).toBeTruthy();
    expect(screen.getByText('沪深300')).toBeTruthy();
    expect(screen.getByTestId('line-rate')).toBeTruthy();
  });

  it('默认隐藏的指数 chip 点击后切换为显示', () => {
    render(<IndexCompareChart market={market} indices={indices} />);
    const chip = screen.getByText('沪深300').closest('button')!;
    // 000300 在 DEFAULT_HIDDEN → opacity-30
    expect(chip.className).toContain('opacity-30');
    fireEvent.click(chip);
    expect(chip.className).toContain('opacity-100');
    // 对应 Line hide 由 true → false
    expect(screen.getByTestId('line-000300').getAttribute('data-hide')).toBe('false');
  });

  it('默认显示的上证指数点击后切换为隐藏', () => {
    render(<IndexCompareChart market={market} indices={indices} />);
    const chip = screen.getByText('上证指数').closest('button')!;
    expect(chip.className).toContain('opacity-100');
    expect(screen.getByTestId('line-000001').getAttribute('data-hide')).toBe('false');
    fireEvent.click(chip);
    expect(chip.className).toContain('opacity-30');
    expect(screen.getByTestId('line-000001').getAttribute('data-hide')).toBe('true');
  });

  it('宽度图例项 disabled, 不可切换', () => {
    render(<IndexCompareChart market={market} indices={indices} />);
    const chip = screen.getByText('宽度站上率').closest('button')!;
    expect(chip.disabled).toBe(true);
    expect(chip.className).toContain('opacity-100');
  });

  it('? 按钮显示帮助说明', () => {
    render(<IndexCompareChart market={market} indices={indices} />);
    fireEvent.click(screen.getByLabelText(/宽度 vs.*说明/));
    expect(screen.getByText(/背离/)).toBeInTheDocument();
  });
});
