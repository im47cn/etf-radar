import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QuadrantLegend } from '../QuadrantLegend';

describe('QuadrantLegend', () => {
  it('renders 4 quadrant labels', () => {
    render(<QuadrantLegend />);
    expect(screen.getByText(/持续强势/)).toBeInTheDocument();
    expect(screen.getByText(/新崛起/)).toBeInTheDocument();
    expect(screen.getByText(/持续弱势/)).toBeInTheDocument();
    expect(screen.getByText(/退潮/)).toBeInTheDocument();
  });

  it('renders explanation text for each quadrant', () => {
    render(<QuadrantLegend />);
    expect(screen.getByText(/长期&短期都强/)).toBeInTheDocument();
    expect(screen.getByText(/长期弱但短期突涨/)).toBeInTheDocument();
    expect(screen.getByText(/长期强但短期跌/)).toBeInTheDocument();
    expect(screen.getByText(/长期&短期都弱/)).toBeInTheDocument();
  });
});
