import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeBubbleTooltip } from '../ThemeBubbleTooltip';
import type { Theme } from '@/types/themes';

const mockTheme: Theme = {
  id: 'storage_dram',
  name: '存储芯片',
  us_etfs: ['DRAM', 'SOXX', 'SMH'],
  primary_us: 'DRAM',
  tags: ['DRAM', 'NAND', '半导体'],
  note: '',
  returns: { r_1d: -0.0017, r_5d: 0.1529, r_20d: 0.1895, r_60d: null, r_120d: null, r_ytd: 0.8509 },
  strength: { short: 99, mid: 93, long: 99, composite: 97 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
};

describe('ThemeBubbleTooltip', () => {
  it('renders nothing when inactive', () => {
    const { container } = render(
      <ThemeBubbleTooltip active={false} payload={[]} theme={mockTheme} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders theme name and ranks when active', () => {
    render(
      <ThemeBubbleTooltip active payload={[{ payload: { themeId: 'storage_dram' } }]} theme={mockTheme} />
    );
    expect(screen.getByText('存储芯片')).toBeInTheDocument();
    expect(screen.getByText(/composite 97/)).toBeInTheDocument();
    expect(screen.getByText(/strength.short 99/)).toBeInTheDocument();
  });

  it('renders formatted returns', () => {
    render(
      <ThemeBubbleTooltip active payload={[{ payload: { themeId: 'storage_dram' } }]} theme={mockTheme} />
    );
    expect(screen.getByText(/-0.17%/)).toBeInTheDocument();
    expect(screen.getByText(/\+15.29%/)).toBeInTheDocument();
    expect(screen.getByText(/\+85.09%/)).toBeInTheDocument();
  });

  it('renders tags and primary ETF', () => {
    render(
      <ThemeBubbleTooltip active payload={[{ payload: { themeId: 'storage_dram' } }]} theme={mockTheme} />
    );
    expect(screen.getByText(/DRAM, NAND, 半导体/)).toBeInTheDocument();
    expect(screen.getByText(/DRAM \+ SOXX, SMH/)).toBeInTheDocument();
  });
});
