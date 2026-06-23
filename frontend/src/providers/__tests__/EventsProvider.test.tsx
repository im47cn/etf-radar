import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { EventsProvider } from '../EventsProvider';
import { useUserEvents } from '@/hooks/useUserEvents';
import type { UserEvent } from '@/lib/portfolio/eventTypes';

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => mockSupabase,
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'u1' }, status: 'authenticated' }),
}));

const mockEvents: UserEvent[] = [
  {
    id: 'e1',
    user_id: 'u1',
    event_type: 'theme_quadrant_change',
    theme_id: 'cn_tech',
    event_signature: 'sig1',
    payload: { from: 'leading', to: 'weakening' },
    asof_date: '2026-06-23',
    created_at: new Date().toISOString(),
    read_at: null,
  },
  {
    id: 'e2',
    user_id: 'u1',
    event_type: 'theme_signal_change',
    theme_id: 'cn_chem',
    event_signature: 'sig2',
    payload: { from: 'resonance', to: 'divergence' },
    asof_date: '2026-06-23',
    created_at: new Date(Date.now() - 100 * 86400_000).toISOString(),
    read_at: null,
  },
];

const channelMock = {
  on: vi.fn().mockReturnThis(),
  subscribe: vi.fn().mockReturnThis(),
};

const mockSupabase = {
  channel: vi.fn(() => channelMock),
  removeChannel: vi.fn(),
  from: vi.fn(() => ({
    select: vi.fn(() => ({
      order: vi.fn(() => ({
        limit: vi.fn().mockResolvedValue({ data: mockEvents, error: null }),
      })),
    })),
  })),
};

function Probe() {
  const { events, unreadCount } = useUserEvents();
  return (
    <div>
      <div data-testid="count">{events.length}</div>
      <div data-testid="unread">{unreadCount}</div>
    </div>
  );
}

describe('EventsProvider', () => {
  it('登录后拉取并过滤 90 天外事件', async () => {
    render(<EventsProvider><Probe /></EventsProvider>);
    await waitFor(() => {
      expect(screen.getByTestId('count').textContent).toBe('1');
      expect(screen.getByTestId('unread').textContent).toBe('1');
    });
  });
});
