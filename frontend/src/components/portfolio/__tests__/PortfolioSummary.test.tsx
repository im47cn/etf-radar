import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PortfolioSummary } from '../PortfolioSummary';
import type { HoldingScore } from '@/lib/portfolio/types';

const mk = (overrides: Partial<HoldingScore>): HoldingScore => ({
  etfCode: 'X', status: 'covered',
  shares: 100, costPrice: 1.0, currentPrice: 1.5,
  marketValue: 150, pnlAbs: 50, pnlPct: 0.5,
  l2Tag: '偏强',
  ...overrides,
} as HoldingScore);

describe('PortfolioSummary', () => {
  it('全 covered: 汇总市值与盈亏', () => {
    render(<PortfolioSummary scores={[
      mk({ marketValue: 1000, pnlAbs: 100, pnlPct: 0.11 }),
      mk({ marketValue: 2000, pnlAbs: -50, pnlPct: -0.03 }),
    ]} />);
    expect(screen.getByText(/¥3,000/)).toBeInTheDocument();
    expect(screen.getByText('覆盖率')).toBeInTheDocument();
    expect(screen.getByText('2 / 2')).toBeInTheDocument();
  });

  it('混合: 总市值仅含 covered, 附加 uncovered 数量', () => {
    render(<PortfolioSummary scores={[
      mk({ marketValue: 1000, pnlAbs: 100 }),
      mk({ status: 'uncovered', marketValue: null, pnlAbs: null }),
    ]} />);
    expect(screen.getByText(/¥1,000/)).toBeInTheDocument();
    expect(screen.getByText(/另含.*1.*只.*无估值/)).toBeInTheDocument();
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
  });
});
