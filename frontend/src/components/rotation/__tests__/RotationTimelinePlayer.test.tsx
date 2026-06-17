import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { SWRConfig } from 'swr';
import React from 'react';
import { server } from '@/mocks/server';
import { RotationTimelinePlayer } from '../RotationTimelinePlayer';
import { mkThemes } from '@/__fixtures__/snapshots';

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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPlayer = () =>
  render(
    <MemoryRouter>
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <RotationTimelinePlayer fallbackThemes={mkThemes(14)} />
      </SWRConfig>
    </MemoryRouter>,
  );

describe('RotationTimelinePlayer (integration)', () => {
  it('renders banner + fallback static scatter when index-error', async () => {
    server.use(http.get('*/snapshots-index.json', () => HttpResponse.error()));
    renderPlayer();
    expect(await screen.findByText(/时间轴数据不可用/)).toBeInTheDocument();
    expect(screen.getByTestId('rc-container')).toBeInTheDocument();
  });

  it('toggling trails on adds Top-5 trail series', async () => {
    renderPlayer();
    await waitFor(() => screen.getByRole('slider'));
    expect(screen.getAllByTestId('scatter')).toHaveLength(1);
    await userEvent.click(screen.getByLabelText('显示尾迹'));
    await waitFor(() => {
      expect(screen.getAllByTestId('scatter').length).toBeGreaterThan(1);
    });
  });

  it('smoke: clicking play eventually advances slider', async () => {
    renderPlayer();
    const slider = await screen.findByRole('slider');
    const initialValue = (slider as HTMLInputElement).value;
    await userEvent.click(screen.getByLabelText('播放'));
    await waitFor(
      () => expect((slider as HTMLInputElement).value).not.toBe(initialValue),
      { timeout: 2000 },
    );
  });
});
