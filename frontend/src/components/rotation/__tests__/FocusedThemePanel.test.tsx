import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { FocusedThemePanel } from '../FocusedThemePanel';
import type { Theme } from '@/types/themes';

const themeAI: Theme = {
  id: 'ai',
  name: 'AI 主题',
  us_etfs: ['SOXX', 'SMH'],
  primary_us: 'SOXX',
  tags: ['tech'],
  note: '',
  returns: { r_1d: 0.01, r_5d: 0.05, r_20d: 0.32, r_60d: 0.1, r_120d: 0.2, r_ytd: 0.4 },
  strength: { short: 90, mid: 85, long: 80, composite: 97 },
  rank: { short: 1, mid: 2, long: 3, composite: 1 },
};

describe('FocusedThemePanel', () => {
  it('does not render when theme is null', () => {
    const { container } = render(<FocusedThemePanel theme={null} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders theme name, quadrant, strength, rank, 20d return', () => {
    render(<FocusedThemePanel theme={themeAI} onClose={() => {}} />);
    expect(screen.getByText('AI 主题')).toBeInTheDocument();
    expect(screen.getByText(/97/)).toBeInTheDocument();
    expect(screen.getByText(/#1/)).toBeInTheDocument();
    expect(screen.getByText(/\+32/)).toBeInTheDocument();
  });

  it('renders ETF chips (decorative, no click handler)', () => {
    render(<FocusedThemePanel theme={themeAI} onClose={() => {}} />);
    expect(screen.getByText(/SOXX/)).toBeInTheDocument();
    expect(screen.getByText('SMH')).toBeInTheDocument();
  });

  it('close button calls onClose', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<FocusedThemePanel theme={themeAI} onClose={onClose} />);
    await user.click(screen.getByRole('button', { name: /关闭/ }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
