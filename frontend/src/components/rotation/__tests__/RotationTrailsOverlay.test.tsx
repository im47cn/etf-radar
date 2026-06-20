import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { RotationTrailsOverlay } from '../RotationTrailsOverlay';
import { UIStateProvider } from '@/providers/UIStateProvider';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

vi.mock('../RotationScatterWithTrails', () => ({
  RotationScatterWithTrails: ({
    themes,
    focusedId,
    onFocus,
  }: {
    themes: Theme[];
    focusedId: string | null;
    onFocus: (id: string) => void;
  }) => (
    <div data-testid="scatter-mock" data-focused={focusedId ?? ''}>
      {themes.map(t => (
        <button
          key={t.id}
          type="button"
          data-testid={`bubble-${t.id}`}
          onClick={() => onFocus(t.id)}
        >
          {t.name}
        </button>
      ))}
    </div>
  ),
}));

const mkTheme = (id: string, long: number, short: number): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: ['ETF1'],
  primary_us: 'ETF1',
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short, mid: 50, long, composite: 50 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

const themes = [mkTheme('ai', 70, 80), mkTheme('semi', 30, 40)];
const snapshots: SnapshotFrame[] = Array.from({ length: 20 }, (_, i) => ({
  date: `2026-01-${String(i + 1).padStart(2, '0')}`,
  themes,
}));

const wrap = (ui: ReactElement) =>
  render(
    <MemoryRouter>
      <UIStateProvider>{ui}</UIStateProvider>
    </MemoryRouter>,
  );

describe('RotationTrailsOverlay', () => {
  it('renders TrailRangeSlider + scatter + no panel by default', () => {
    wrap(<RotationTrailsOverlay themes={themes} snapshots={snapshots} />);
    expect(screen.getByText(/轨迹长度/)).toBeInTheDocument();
    expect(screen.getByTestId('scatter-mock')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /主题详情面板/ })).not.toBeInTheDocument();
  });

  it('disables slider when snapshots is empty', () => {
    const { container } = wrap(<RotationTrailsOverlay themes={themes} snapshots={[]} />);
    expect(container.querySelector('[data-disabled]')).not.toBeNull();
  });

  it('opens FocusedThemePanel after clicking a bubble', async () => {
    const user = userEvent.setup();
    wrap(<RotationTrailsOverlay themes={themes} snapshots={snapshots} />);
    await user.click(screen.getByTestId('bubble-ai'));
    expect(screen.getByRole('region', { name: /主题详情面板/ })).toBeInTheDocument();
  });

  it('ESC closes the focused panel', async () => {
    const user = userEvent.setup();
    wrap(<RotationTrailsOverlay themes={themes} snapshots={snapshots} />);
    await user.click(screen.getByTestId('bubble-ai'));
    expect(screen.getByRole('region', { name: /主题详情面板/ })).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(screen.queryByRole('region', { name: /主题详情面板/ })).not.toBeInTheDocument();
  });
});
