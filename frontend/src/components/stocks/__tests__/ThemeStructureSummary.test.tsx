import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ThemeStructureSummary } from '../ThemeStructureSummary';
import type { AggregatedStock } from '@/types/holdings';

function s(code: string, strength60: number | null, leader = ''): AggregatedStock {
  return {
    code, name: code, cumulativeWeight: 1, sourceEtfs: ['x'], spot: null,
    indicators: {
      name: code, strength_60d: strength60, strength_20d: null,
      rsi_14: null, vol_ratio: null,
      leader: leader as '⭐⭐⭐' | '⭐⭐' | '⭐' | '',
    },
  };
}

describe('ThemeStructureSummary', () => {
  it('renders diagnosis text', () => {
    const stocks = ['a', 'b', 'c', 'd', 'e', 'f'].map(c => s(c, 75));
    render(<ThemeStructureSummary stocks={stocks} />);
    expect(screen.getByText(/全面走强/)).toBeInTheDocument();
  });

  it('shows 3-star leader count and ratio', () => {
    const stocks = [s('a', 90, '⭐⭐⭐'), s('b', 80, '⭐⭐'), s('c', 60)];
    render(<ThemeStructureSummary stocks={stocks} />);
    expect(screen.getByText(/⭐⭐⭐.*1/)).toBeInTheDocument();
  });

  it('shows fallback when no indicators', () => {
    const stocks = [{ code: 'x', name: 'x', cumulativeWeight: 1,
                      sourceEtfs: ['x'], spot: null } as AggregatedStock];
    render(<ThemeStructureSummary stocks={stocks} />);
    expect(screen.getByText(/暂无指标数据/)).toBeInTheDocument();
  });
});
