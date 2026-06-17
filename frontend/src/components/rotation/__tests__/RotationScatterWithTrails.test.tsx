import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RotationScatterWithTrails } from '../RotationScatterWithTrails';
import { mkThemes, mkFrame } from '@/__fixtures__/snapshots';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="rc-container" style={{ width: 800, height: 500 }}>{children}</div>
    ),
    ScatterChart: ({ children }: { children: React.ReactNode }) => (
      <svg data-testid="scatter-chart">{children}</svg>
    ),
    Scatter: ({ children, name }: { children?: React.ReactNode; name?: string }) => (
      <g data-testid="scatter" data-name={name}>{children}</g>
    ),
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    ReferenceLine: () => null,
    ReferenceArea: () => null,
    Tooltip: () => null,
    Cell: () => null,
    LabelList: () => null,
  };
});

const renderWithRouter = (ui: React.ReactNode) =>
  render(<MemoryRouter>{ui}</MemoryRouter>);

describe('RotationScatterWithTrails', () => {
  it('renders only main scatter when showTrails=false', () => {
    const themes = mkThemes(14);
    renderWithRouter(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={[]}
        topThemeIds={new Set()}
        animationDuration={300}
        showTrails={false}
      />,
    );
    expect(screen.getAllByTestId('scatter')).toHaveLength(1);
  });

  it('renders 1 main + N trail scatters when showTrails=true', () => {
    const themes = mkThemes(14);
    const trailFrames = [mkFrame('2026-01-01'), mkFrame('2026-01-02')];
    const topThemeIds = new Set(['t0', 't1', 't2', 't3', 't4']);
    renderWithRouter(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={trailFrames}
        topThemeIds={topThemeIds}
        animationDuration={300}
        showTrails={true}
      />,
    );
    expect(screen.getAllByTestId('scatter')).toHaveLength(6);
  });

  it('handles empty themes without crash', () => {
    renderWithRouter(
      <RotationScatterWithTrails
        themes={[]}
        trailFrames={[]}
        topThemeIds={new Set()}
        animationDuration={300}
        showTrails={false}
      />,
    );
    expect(screen.getByTestId('rc-container')).toBeInTheDocument();
  });
});
