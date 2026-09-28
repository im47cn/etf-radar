import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useSubscription } from '../useSubscription';

// maybeSingle() 的返回可按用例改写
const maybeSingleMock = vi.fn();
const eqMock = vi.fn(() => ({ maybeSingle: maybeSingleMock }));
const selectMock = vi.fn(() => ({ eq: eqMock }));

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => ({
    from: vi.fn(() => ({ select: selectMock })),
  }),
}));

// useAuth 可被各用例覆盖
const mockAuthState = { user: { id: 'u1' } as { id: string } | null, status: 'authenticated' as string };
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => mockAuthState,
}));

const future = new Date(Date.now() + 30 * 86400_000).toISOString();
const past   = new Date(Date.now() - 1 * 86400_000).toISOString();

const mkSub = (over: Record<string, unknown>) => ({
  id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
  user_id: 'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e',
  plan: 'monthly',
  status: 'active',
  current_period_end: future,
  source: 'afdian',
  afdian_trade_no: null,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
  ...over,
});

beforeEach(() => {
  mockAuthState.user = { id: 'u1' };
  mockAuthState.status = 'authenticated';
  maybeSingleMock.mockReset();
});

describe('useSubscription', () => {
  it('active 且未过期 → member', async () => {
    maybeSingleMock.mockResolvedValue({ data: mkSub({}), error: null });
    const { result } = renderHook(() => useSubscription());
    await waitFor(() => expect(result.current.state).toBe('member'));
    expect(result.current.plan).toBe('monthly');
    expect(result.current.periodEnd).toBe(future);
  });

  it('无订阅行 → non-member', async () => {
    maybeSingleMock.mockResolvedValue({ data: null, error: null });
    const { result } = renderHook(() => useSubscription());
    await waitFor(() => expect(result.current.state).toBe('non-member'));
    expect(result.current.plan).toBeNull();
  });

  it('active 但已过期 → non-member（到期回落）', async () => {
    maybeSingleMock.mockResolvedValue({ data: mkSub({ current_period_end: past }), error: null });
    const { result } = renderHook(() => useSubscription());
    await waitFor(() => expect(result.current.state).toBe('non-member'));
  });

  it('查询错误 → error（不得降级为 non-member 静默锁会员）', async () => {
    maybeSingleMock.mockResolvedValue({ data: null, error: new Error('network down') });
    const { result } = renderHook(() => useSubscription());
    await waitFor(() => expect(result.current.state).toBe('error'));
    expect(result.current.plan).toBeNull();
  });

  it('行形状 schema 不符 → error', async () => {
    maybeSingleMock.mockResolvedValue({ data: { id: 'not-a-sub' }, error: null });
    const { result } = renderHook(() => useSubscription());
    await waitFor(() => expect(result.current.state).toBe('error'));
  });

  it('查询 throw（网络异常）→ error 而非降级 non-member', async () => {
    maybeSingleMock.mockRejectedValue(new Error('fetch failed'));
    const { result } = renderHook(() => useSubscription());
    await waitFor(() => expect(result.current.state).toBe('error'));
    expect(result.current.plan).toBeNull();
    expect(result.current.periodEnd).toBeNull();
  });

  it('未登录 → non-member 且不查库', async () => {
    mockAuthState.user = null;
    mockAuthState.status = 'anonymous';
    const { result } = renderHook(() => useSubscription());
    await waitFor(() => expect(result.current.state).toBe('non-member'));
    expect(maybeSingleMock).not.toHaveBeenCalled();
  });
});
