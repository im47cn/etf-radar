import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { EventsProvider } from '../EventsProvider';
import { useUserEvents } from '@/hooks/useUserEvents';

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => mockSupabase,
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'u1' }, status: 'authenticated' }),
}));

// 模拟 Supabase 返回的原始 jsonb 行（典型情况 + 边界情况：缺 version、超 90 天）
const mockEvents: unknown[] = [
  {
    id: 'e1',
    user_id: 'u1',
    event_type: 'theme_quadrant_change',
    theme_id: 'cn_tech',
    event_signature: 'sig1',
    payload: { version: 1, from: 'leading', to: 'weakening', etf_codes: ['SOXX'] },
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
    // 故意省略 version：验证 zod default(1) 兼容历史 jsonb 行
    payload: { from: 'resonance', to: 'divergence', etf_codes: ['159870'] },
    asof_date: '2026-06-23',
    created_at: new Date().toISOString(),                  // 在 90 天窗口内
    read_at: null,
  },
  {
    id: 'e3',
    user_id: 'u1',
    event_type: 'theme_quadrant_change',
    theme_id: 'cn_old',
    event_signature: 'sig3',
    payload: { version: 1, from: 'weak', to: 'leading', etf_codes: ['XYZ'] },
    asof_date: '2026-03-15',
    created_at: new Date(Date.now() - 100 * 86400_000).toISOString(),  // 超 90 天，被过滤
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
  it('登录后拉取：window 内 2 条均可见（含缺 version 的兼容行），window 外 1 条被过滤', async () => {
    render(<EventsProvider><Probe /></EventsProvider>);
    await waitFor(() => {
      // e1 + e2 在窗口内（含 e2 验证 zod default(1) 兼容历史行）;e3 被 90 天过滤
      expect(screen.getByTestId('count').textContent).toBe('2');
      expect(screen.getByTestId('unread').textContent).toBe('2');
    });
  });
});
