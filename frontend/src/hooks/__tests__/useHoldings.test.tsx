import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AuthContext } from '@/providers/authContext';
import { useHoldings } from '../useHoldings';
import { HoldingsProvider } from '@/providers/HoldingsProvider';
import type { ReactNode } from 'react';

const fakeHoldings = [
  { id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d', user_id: 'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e', etf_code: '512480', shares: 100, cost_price: 2.0, note: null, created_at: '2026-01-01', updated_at: '2026-01-01' },
];

const orderMock = vi.fn();
const upsertMock = vi.fn();
const deleteMock = vi.fn();
const updateFinalMock = vi.fn();
const updatePayloadMock = vi.fn();
const channelMock = vi.fn();

// select() 返回带 order() 的链式对象，order() 才真正 resolve 数据
const selectMock = vi.fn(() => ({ order: orderMock }));

// update(payload).eq('user_id', ...).eq('etf_code', ...) — 双 eq 链
const updateChain = () => ({
  eq: vi.fn(() => ({ eq: updateFinalMock })),
});

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => ({
    from: vi.fn(() => ({
      select: selectMock,
      upsert: upsertMock,
      delete: () => ({ eq: deleteMock }),
      update: (payload: unknown) => { updatePayloadMock(payload); return updateChain(); },
    })),
    channel: channelMock,
    removeChannel: vi.fn(),
  }),
}));

const wrapper = (status: 'authenticated' | 'anonymous') => ({ children }: { children: ReactNode }) => (
  <AuthContext.Provider value={{
    status,
    user: status === 'authenticated' ? { id: 'u', email: 't@e.com' } as never : null,
    signInWithMagicLink: vi.fn(),
    signInWithGoogle:    vi.fn(),
    signInWithGithub:    vi.fn(),
    signOut:             vi.fn(),
  }}>
    <HoldingsProvider>{children}</HoldingsProvider>
  </AuthContext.Provider>
);

describe('useHoldings', () => {
  beforeEach(() => {
    selectMock.mockReset();
    selectMock.mockReturnValue({ order: orderMock });
    orderMock.mockReset();
    updateFinalMock.mockReset();
    updatePayloadMock.mockReset();
    channelMock.mockReset();
    channelMock.mockReturnValue({
      on: () => ({ subscribe: vi.fn(() => ({ unsubscribe: vi.fn() })) }),
    });
  });

  it('anonymous: 返回空数组 + loading=false', () => {
    const { result } = renderHook(() => useHoldings(), { wrapper: wrapper('anonymous') });
    expect(result.current.holdings).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it('authenticated: 拉取持仓', async () => {
    orderMock.mockResolvedValue({ data: fakeHoldings, error: null });
    const { result } = renderHook(() => useHoldings(), { wrapper: wrapper('authenticated') });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.holdings).toHaveLength(1);
    expect(result.current.holdings[0].etf_code).toBe('512480');
  });

  it('update: 仅传入字段被发送, 不影响 etf_code', async () => {
    orderMock.mockResolvedValue({ data: fakeHoldings, error: null });
    updateFinalMock.mockResolvedValue({ error: null });
    const { result } = renderHook(() => useHoldings(), { wrapper: wrapper('authenticated') });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      const r = await result.current.update('512480', { shares: 200, note: '修正' });
      expect(r.error).toBeNull();
    });
    expect(updatePayloadMock).toHaveBeenCalledWith({ shares: 200, note: '修正' });
  });

  it('update: 空 patch 直接返回, 不发请求', async () => {
    orderMock.mockResolvedValue({ data: fakeHoldings, error: null });
    const { result } = renderHook(() => useHoldings(), { wrapper: wrapper('authenticated') });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      const r = await result.current.update('512480', {});
      expect(r.error).toBeNull();
    });
    expect(updatePayloadMock).not.toHaveBeenCalled();
  });

  it('update: anonymous 状态返回 "未登录"', async () => {
    const { result } = renderHook(() => useHoldings(), { wrapper: wrapper('anonymous') });
    await act(async () => {
      const r = await result.current.update('512480', { shares: 100 });
      expect(r.error).toBe('未登录');
    });
  });
});
