import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EventItem } from '../EventItem';
import type { UserEvent } from '@/lib/portfolio/eventTypes';

const mk = (overrides: Partial<UserEvent> = {}): UserEvent => ({
  id: 'e1', user_id: 'u1', event_type: 'theme_quadrant_change',
  theme_id: 'cn_tech', event_signature: 'sig',
  payload: { from: 'weak', to: 'leading' },
  asof_date: '2026-06-23',
  created_at: '2026-06-23T01:00:00Z', read_at: null,
  ...overrides,
} as UserEvent);

describe('EventItem', () => {
  it('象限切到 leading 显示利好（🟢）', () => {
    render(<EventItem event={mk()} themeName="科技" />);
    expect(screen.getByText(/科技/)).toBeInTheDocument();
    expect(screen.getByText(/领涨|强势/)).toBeInTheDocument();
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('象限切到 weak 显示利空（🔴）', () => {
    render(<EventItem event={mk({
      event_type: 'theme_quadrant_change',
      payload: { from: 'leading', to: 'weak' },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'red');
  });

  it('强度上穿显示利好', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_up',
      payload: { threshold: 75, from: 70, to: 80 },
    })} themeName="科技" />);
    expect(screen.getByText(/上穿|强势区/)).toBeInTheDocument();
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('信号变共振显示利好', () => {
    render(<EventItem event={mk({
      event_type: 'theme_signal_change',
      payload: { from: 'divergence', to: 'resonance' },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('已读样式：灰底', () => {
    render(<EventItem event={mk({ read_at: '2026-06-23T02:00:00Z' })} themeName="科技" />);
    const root = screen.getByTestId('event-root');
    expect(root.className).toMatch(/bg-gray-50|opacity-/);
  });

  it('文案保持 L1+L2 立场（不含"买入/推荐"）', () => {
    render(<EventItem event={mk()} themeName="科技" />);
    const txt = document.body.textContent ?? '';
    expect(txt).not.toMatch(/推荐买入|建议买入|可买/);
  });
});
