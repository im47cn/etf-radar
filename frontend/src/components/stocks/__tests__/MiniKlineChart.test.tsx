import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MiniKlineChart } from '../MiniKlineChart';

let fetchSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => { fetchSpy = vi.spyOn(globalThis, 'fetch'); });
afterEach(() => { fetchSpy.mockRestore(); vi.clearAllMocks(); });

describe('MiniKlineChart', () => {
  it('shows loading then renders SVG with bars', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify({
      code: '002129', name: 'TCL', generated_at: '...',
      bars: [
        { date: '2026-04-01', o: 10, h: 11, l: 9.5, c: 10.5, v: 100 },
        { date: '2026-04-02', o: 10.5, h: 11.2, l: 10.3, c: 10.8, v: 110 },
        { date: '2026-04-03', o: 10.8, h: 11, l: 10.5, c: 10.6, v: 90 },
        { date: '2026-04-04', o: 10.6, h: 10.9, l: 10.4, c: 10.7, v: 95 },
        { date: '2026-04-05', o: 10.7, h: 11.0, l: 10.5, c: 10.9, v: 105 },
      ],
    })));
    const { container } = render(<MiniKlineChart code="002129" />);
    await waitFor(() => expect(container.querySelector('svg')).toBeInTheDocument());
    const rects = container.querySelectorAll('svg rect');
    expect(rects.length).toBeGreaterThanOrEqual(3);
  });

  it('shows "数据不足" when bars < 5', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify({
      code: '002130', name: 'x', generated_at: '...',
      bars: [{ date: '2026-04-01', o: 10, h: 11, l: 9, c: 10.5, v: 100 }],
    })));
    render(<MiniKlineChart code="002130" />);
    await waitFor(() => expect(screen.getByText(/数据不足/)).toBeInTheDocument());
  });

  it('shows "无数据" on 404', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('', { status: 404 }));
    render(<MiniKlineChart code="002131" />);
    await waitFor(() => expect(screen.getByText(/无数据/)).toBeInTheDocument());
  });
});
