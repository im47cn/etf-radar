import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useWatchlist } from '../useWatchlist';
import { NotAMemberError } from '../types';

const orderMock  = vi.fn();
const selectMock = vi.fn(() => ({ order: orderMock }));
const deleteEqMock = vi.fn();
const rpcMock = vi.fn();

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => ({
    from: vi.fn(() => ({
      select: selectMock,
      delete: () => ({ eq: deleteEqMock }),
    })),
    rpc: rpcMock,
  }),
}));

const mockAuthState = { user: { id: 'u1' } as { id: string } | null, status: 'authenticated' as string };
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => mockAuthState,
  useAuthOptional: () => mockAuthState,
}));

const fakeItems = [
  { id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d', user_id: 'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e', item_type: 'theme', item_key: 'cn_tech', created_at: '2026-01-01' },
];

beforeEach(() => {
  mockAuthState.user = { id: 'u1' };
  mockAuthState.status = 'authenticated';
  orderMock.mockReset();
  deleteEqMock.mockReset();
  rpcMock.mockReset();
  orderMock.mockResolvedValue({ data: fakeItems, error: null });
});

describe('useWatchlist', () => {
  it('authenticated: 拉取自选列表', async () => {
    const { result } = renderHook(() => useWatchlist());
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.items[0].item_key).toBe('cn_tech');
  });

  it('add: 会员成功 → 调 add_watchlist RPC 并刷新', async () => {
    rpcMock.mockResolvedValue({ data: {}, error: null });
    const { result } = renderHook(() => useWatchlist());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      const r = await result.current.add('etf', '512480');
      expect(r.error).toBeNull();
    });
    expect(rpcMock).toHaveBeenCalledWith('add_watchlist', { p_item_type: 'etf', p_item_key: '512480' });
  });

  it('add: 非会员 → 抛 NotAMemberError', async () => {
    rpcMock.mockResolvedValue({ data: null, error: { message: 'NOT_A_MEMBER' } });
    const { result } = renderHook(() => useWatchlist());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await expect(result.current.add('etf', '512480')).rejects.toBeInstanceOf(NotAMemberError);
    });
  });

  it('remove: 删除并刷新', async () => {
    deleteEqMock.mockResolvedValue({ error: null });
    const { result } = renderHook(() => useWatchlist());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      const r = await result.current.remove('a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d');
      expect(r.error).toBeNull();
    });
    expect(deleteEqMock).toHaveBeenCalledWith('id', 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d');
  });

  it('anonymous: 返回空列表', async () => {
    mockAuthState.user = null;
    mockAuthState.status = 'anonymous';
    const { result } = renderHook(() => useWatchlist());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toEqual([]);
  });
});
