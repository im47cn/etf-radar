import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StockTable } from '../StockTable';
import type { AggregatedStock } from '@/types/holdings';

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

  it('uses blue for positive r_1d and red for negative (matches ThemeRow)', () => {
    const { container, rerender } = render(
      <StockTable stocks={[row({ spot: { name: 'x', close: 1, r_1d: 0.01 } })]} />
    );
    expect(container.querySelector('.text-blue-600')).toBeInTheDocument();
    rerender(<StockTable stocks={[row({ spot: { name: 'x', close: 1, r_1d: -0.01 } })]} />);
    expect(container.querySelector('.text-red-600')).toBeInTheDocument();
  });
});
