import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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
    // update 链: .update({...}).eq('user_id', ...).is('read_at', null) → resolve
    update: vi.fn(() => ({
      eq: vi.fn(() => ({
        is: vi.fn().mockResolvedValue({ error: null }),
      })),
    })),
    // upsert 链: .upsert(rows, opts).select('id') → resolve
    upsert: vi.fn(() => ({
      select: vi.fn().mockResolvedValue({ data: [], error: null }),
    })),
  })),
};

function Probe({ showMutations = false }: { showMutations?: boolean }) {
  const { events, unreadCount, upsertEvents, markRead, markAllRead, loading, error } = useUserEvents();
  return (
    <div>
      <div data-testid="count">{events.length}</div>
      <div data-testid="unread">{unreadCount}</div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="error">{error ?? ''}</div>
      {showMutations && (
        <>
          <button data-testid="upsert" onClick={() => upsertEvents([])} />
          <button data-testid="mark-read" onClick={() => markRead([])} />
          <button data-testid="mark-all" onClick={() => markAllRead()} />
        </>
      )}
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

  it('upsertEvents 空数组直接返回 inserted=0', async () => {
    render(<EventsProvider><Probe showMutations /></EventsProvider>);
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('2'));
    const btn = screen.getByTestId('upsert');
    // 不抛错即可 — 空数组走 early return 分支
    expect(() => fireEvent.click(btn)).not.toThrow();
  });

  it('markRead 空数组直接返回', async () => {
    render(<EventsProvider><Probe showMutations /></EventsProvider>);
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('2'));
    expect(() => fireEvent.click(screen.getByTestId('mark-read'))).not.toThrow();
  });

  it('markAllRead 可调用', async () => {
    render(<EventsProvider><Probe showMutations /></EventsProvider>);
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('2'));
    expect(() => fireEvent.click(screen.getByTestId('mark-all'))).not.toThrow();
  });
});

describe('EventsProvider — fetch error 分支', () => {
  beforeEach(() => {
    mockSupabase.from = vi.fn(() => ({
      select: vi.fn(() => ({
        order: vi.fn(() => ({
          limit: vi.fn().mockResolvedValue({ data: null, error: { message: 'DB error' } }),
        })),
      })),
      update: vi.fn(() => ({
        eq: vi.fn(() => ({
          is: vi.fn().mockResolvedValue({ error: null }),
        })),
      })),
      upsert: vi.fn(() => ({
        select: vi.fn().mockResolvedValue({ data: [], error: null }),
      })),
    })) as never;
  });

  it('DB 查询返回 error 时设置 error message', async () => {
    render(<EventsProvider><Probe /></EventsProvider>);
    await waitFor(() => {
      expect(screen.getByTestId('error').textContent).toBe('DB error');
    });
  });
});
