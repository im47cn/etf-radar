import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StockTable } from '../StockTable';
import type { AggregatedStock } from '@/types/holdings';
import { useSubscription } from '@/lib/subscription/useSubscription';

vi.mock('@/lib/subscription/useSubscription', () => ({ useSubscription: vi.fn() }));

const withIndicators = (vol: number | null) => row({
  indicators: {
    name: 'TCL中环', strength_60d: 50, strength_20d: 50, rsi_14: 50,
    vol_ratio: 1, leader: '⭐', vol_forecast_ann: vol,
  },
});

beforeEach(() => {
  vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
});

const row = (overrides: Partial<AggregatedStock> = {}): AggregatedStock => ({
  code: '002129',
  name: 'TCL中环',
  cumulativeWeight: 8.5,
  sourceEtfs: ['512480'],
  spot: { name: 'TCL中环', close: 12.5, r_1d: 0.025 },
  ...overrides,
});

describe('StockTable', () => {
  it('renders rows in given order', () => {
    render(<StockTable stocks={[row({ code: 'A' }), row({ code: 'B' })]} />);
    const cells = screen.getAllByRole('row').slice(1).map(r => r.textContent ?? '');
    expect(cells[0]).toContain('A');
    expect(cells[1]).toContain('B');
  });

  it('shows weight with one decimal place', () => {
    render(<StockTable stocks={[row({ cumulativeWeight: 12.345 })]} />);
    expect(screen.getByText('12.3%')).toBeInTheDocument();
  });

  it('shows dash when spot is null', () => {
    render(<StockTable stocks={[row({ spot: null })]} />);
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it('renders source ETFs as chips', () => {
    render(<StockTable stocks={[row({ sourceEtfs: ['512480', '159870'] })]} />);
    expect(screen.getByText('512480')).toBeInTheDocument();
    expect(screen.getByText('159870')).toBeInTheDocument();
  });

  it('uses red for positive r_1d and green for negative (Chinese market red-up/green-down)', () => {
    const { container, rerender } = render(
      <StockTable stocks={[row({ spot: { name: 'x', close: 1, r_1d: 0.01 } })]} />
    );
    expect(container.querySelector('.text-red-600')).toBeInTheDocument();
    rerender(<StockTable stocks={[row({ spot: { name: 'x', close: 1, r_1d: -0.01 } })]} />);
    expect(container.querySelector('.text-green-600')).toBeInTheDocument();
  });

  it('? 按钮显示帮助说明', () => {
    render(<StockTable stocks={[row()]} />);
    fireEvent.click(screen.getByLabelText(/成分股明细.*说明/));
    expect(screen.getByText(/季度披露/)).toBeInTheDocument();
  });

  it('会员显示前瞻波动数值 (年化百分比)', () => {
    render(<StockTable stocks={[withIndicators(0.406)]} />);
    expect(screen.getByText('41%')).toBeInTheDocument();
  });

  it('前瞻波动 >60% 标红', () => {
    const { container } = render(<StockTable stocks={[withIndicators(0.9)]} />);
    expect(container.querySelector('.text-red-600')).toBeInTheDocument();
  });

  it('非会员前瞻波动列锁定为 🔒', () => {
    vi.mocked(useSubscription).mockReturnValue({ state: 'active' } as never);
    render(<StockTable stocks={[withIndicators(0.406)]} />);
    expect(screen.getAllByText('🔒').length).toBeGreaterThanOrEqual(1);
  });

  it('前瞻波动 null 显示 —', () => {
    render(<StockTable stocks={[withIndicators(null)]} />);
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
  });
});
