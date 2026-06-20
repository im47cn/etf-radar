import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { RotationTrailsOverlay } from '../RotationTrailsOverlay';
import { UIStateProvider } from '@/providers/UIStateProvider';
import type { Theme, Strength } from '@/types/themes';
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

interface MkThemeOpts {
  us_strength?: Strength | null;
  cn_strength?: Strength | null;
  primary_us?: string | null;
}

const sx = (short: number, long: number): Strength => ({
  short,
  mid: 50,
  long,
  composite: 50,
});

const mkTheme = (id: string, long: number, short: number, opts: MkThemeOpts = {}): Theme => {
  const primary_us = 'primary_us' in opts ? opts.primary_us! : 'ETF1';
  return {
    id,
    name: id.toUpperCase(),
    us_etfs: primary_us ? ['ETF1'] : [],
    primary_us,
    tags: [],
    note: '',
    returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
    strength: { short, mid: 50, long, composite: 50 },
    us_strength: opts.us_strength !== undefined ? opts.us_strength : sx(short, long),
    cn_strength: opts.cn_strength !== undefined ? opts.cn_strength : sx(short, long),
    rank: { short: 1, mid: 1, long: 1, composite: 1 },
  };
};

const themes = [mkTheme('ai', 70, 80), mkTheme('semi', 30, 40)];
const snapshots: SnapshotFrame[] = Array.from({ length: 20 }, (_, i) => ({
  date: `2026-01-${String(i + 1).padStart(2, '0')}`,
  themes,
}));

const wrap = (ui: ReactElement, initialEntry: string = '/') =>
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
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

  describe('marketView filtering', () => {
    // fixture: 3 类主题 — mapped (us+cn 双 ETF), us-only, cn-only
    const mapped = mkTheme('mapped', 60, 60);
    const usOnly = mkTheme('us-only', 50, 50, { cn_strength: null });
    const cnOnly = mkTheme('cn-only', 40, 40, { primary_us: null, us_strength: null });
    const mixed = [mapped, usOnly, cnOnly];
    const mixedSnapshots: SnapshotFrame[] = [{ date: '2026-01-01', themes: mixed }];

    const bubbleIds = () =>
      Array.from(document.querySelectorAll<HTMLElement>('[data-testid^="bubble-"]')).map(
        el => el.getAttribute('data-testid'),
      );

    it('mv=us hides cn-only themes from scatter', () => {
      wrap(<RotationTrailsOverlay themes={mixed} snapshots={mixedSnapshots} />, '/?mv=us');
      expect(bubbleIds()).toEqual(['bubble-mapped', 'bubble-us-only']);
    });

    it('mv=cn-all shows every theme with cn_strength (mapped + cn-only)', () => {
      wrap(<RotationTrailsOverlay themes={mixed} snapshots={mixedSnapshots} />, '/?mv=cn-all');
      expect(bubbleIds()).toEqual(['bubble-mapped', 'bubble-cn-only']);
    });

    it('mv=cn-only shows only cn-only themes in scatter', () => {
      wrap(<RotationTrailsOverlay themes={mixed} snapshots={mixedSnapshots} />, '/?mv=cn-only');
      expect(bubbleIds()).toEqual(['bubble-cn-only']);
    });
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
