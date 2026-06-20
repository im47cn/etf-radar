import { render, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { RotationScatterWithTrails } from '../RotationScatterWithTrails';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => (
      <div data-testid="rc-container" style={{ width: 800, height: 500 }}>{children}</div>
    ),
    ScatterChart: ({ children }: { children: ReactNode }) => (
      <svg data-testid="scatter-chart">{children}</svg>
    ),
    Scatter: ({ children, name, onClick }: { children?: ReactNode; name?: string; onClick?: (a: unknown) => void }) => (
      <g
        data-testid="scatter"
        data-name={name}
        onClick={() => onClick?.({ themeId: 'ai' })}
      >
        {children}
      </g>
    ),
    Cell: ({ fill, fillOpacity, stroke, strokeWidth, r }: { fill?: string; fillOpacity?: number; stroke?: string; strokeWidth?: number; r?: number }) => (
      <g
        data-testid="cell"
        data-fill={fill}
        fill-opacity={fillOpacity}
        data-stroke={stroke}
        data-stroke-width={strokeWidth}
        data-r={r}
      />
    ),
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    ReferenceLine: () => null,
    ReferenceArea: () => null,
    Tooltip: () => null,
    LabelList: () => null,
  };
});

const mkTheme = (id: string, long: number, short: number): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: [],
  primary_us: '',
  primary_cn: null,
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short, mid: 50, long, composite: 50 },
  us_strength: { short, mid: 50, long, composite: 50 },
  cn_strength: null,
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

const themes = [mkTheme('ai', 70, 80), mkTheme('semi', 30, 40)];
const trailFrames: SnapshotFrame[] = [
  { date: '2026-01-01', themes: [mkTheme('ai', 65, 75), mkTheme('semi', 25, 35)] },
  { date: '2026-01-02', themes },
];

const wrap = (ui: ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('RotationScatterWithTrails (rewritten)', () => {
  it('renders one main bubble cell per theme (all themes, not top-N)', () => {
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={[]}
        focusedId={null}
        onFocus={() => {}}
      />,
    );
    const mainScatter = container.querySelector('[data-name="current"]');
    expect(mainScatter).not.toBeNull();
    const cells = mainScatter!.querySelectorAll('[data-testid="cell"]');
    expect(cells.length).toBe(2);
  });

  it('calls onFocus(themeId) when clicking the scatter', () => {
    const onFocus = vi.fn();
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={trailFrames}
        focusedId={null}
        onFocus={onFocus}
      />,
    );
    const mainScatter = container.querySelector('[data-name="current"]');
    expect(mainScatter).not.toBeNull();
    fireEvent.click(mainScatter!);
    expect(onFocus).toHaveBeenCalledWith('ai');
  });

  it('dims other (non-focused) themes when focusedId is set', () => {
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={trailFrames}
        focusedId="ai"
        onFocus={() => {}}
      />,
    );
    const mainScatter = container.querySelector('[data-name="current"]')!;
    const dimmed = mainScatter.querySelectorAll('[fill-opacity="0.2"]');
    expect(dimmed.length).toBe(1);
  });

  it('non-focused cells use mid-stroke color with discrete stroke-width tiers', () => {
    // 构造 3 个 mid 值差异明显的 theme: 10/50/90 → 三分位法 q33=50, q67=90 → LOW/MID/HIGH
    const t = (id: string, mid: number): Theme => ({
      ...mkTheme(id, 50, 50),
      us_strength: { short: 50, mid, long: 50, composite: 50 },
      strength: { short: 50, mid, long: 50, composite: 50 },
    });
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={[t('a', 10), t('b', 50), t('c', 90)]}
        trailFrames={[]}
        focusedId={null}
        onFocus={() => {}}
      />,
    );
    const mainScatter = container.querySelector('[data-name="current"]')!;
    const cells = Array.from(mainScatter.querySelectorAll('[data-testid="cell"]'));
    // 全部非聚焦 → 全部走 MID_STROKE_COLOR (#374151)
    cells.forEach(c => expect(c.getAttribute('data-stroke')).toBe('#374151'));
    const widths = cells.map(c => Number(c.getAttribute('data-stroke-width')));
    // 三档线宽 LOW/MID/HIGH 应同时存在
    expect(new Set(widths)).toEqual(new Set([1, 2, 3]));
  });

  it('focused cell uses black stroke (overrides mid stroke)', () => {
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={[]}
        focusedId="ai"
        onFocus={() => {}}
      />,
    );
    const mainScatter = container.querySelector('[data-name="current"]')!;
    const focusedCell = Array.from(
      mainScatter.querySelectorAll('[data-testid="cell"]'),
    ).find(c => c.getAttribute('data-stroke') === '#000');
    expect(focusedCell).toBeDefined();
    expect(focusedCell!.getAttribute('data-stroke-width')).toBe('2');
  });

  it('main bubbles receive explicit r prop (>=8px) to ensure touch hit-area', () => {
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={[]}
        focusedId={null}
        onFocus={() => {}}
      />,
    );
    const mainScatter = container.querySelector('[data-name="current"]')!;
    const cells = Array.from(mainScatter.querySelectorAll('[data-testid="cell"]'));
    cells.forEach(c => {
      const r = Number(c.getAttribute('data-r'));
      // 桌面端最小 8px (computeBubbleSize(0) === 8); 不允许走 Recharts 默认 ~4.5px
      expect(r).toBeGreaterThanOrEqual(8);
    });
  });

  it('renders without crashing when trailFrames is empty', () => {
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={[]}
        focusedId={null}
        onFocus={() => {}}
      />,
    );
    expect(container.querySelector('[data-testid="rc-container"]')).not.toBeNull();
  });
});
