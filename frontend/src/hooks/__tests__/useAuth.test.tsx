import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { AuthProvider } from '@/providers/AuthProvider';
import { AuthContext, type AuthContextValue } from '@/providers/authContext';
import { useAuth, useAuthOptional } from '../useAuth';
import type { ReactNode } from 'react';

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => ({
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      signInWithOtp: vi.fn().mockResolvedValue({ error: null }),
      signInWithOAuth: vi.fn().mockResolvedValue({ error: null }),
    },
  }),
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

describe('useAuth', () => {
  beforeEach(() => vi.clearAllMocks());

  it('initial state: status=loading, user=null', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.status).toBe('loading');
    expect(result.current.user).toBeNull();
  });

  it('exposes signInWithMagicLink, signInWithGoogle, signInWithGithub, signOut', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(typeof result.current.signInWithMagicLink).toBe('function');
    expect(typeof result.current.signInWithGoogle).toBe('function');
    expect(typeof result.current.signInWithGithub).toBe('function');
    expect(typeof result.current.signOut).toBe('function');
  });
});

describe('useAuth — throw 分支', () => {
  it('在 Provider 外抛错', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used within <AuthProvider>',
    );
    spy.mockRestore();
  });
});

describe('useAuthOptional', () => {
  const mockValue = {
    status: 'authenticated',
    user: { id: 'u1', email: 'a@b.com' },
  } as unknown as AuthContextValue;

  it('在 Provider 内返回 context 值', () => {
    const { result } = renderHook(() => useAuthOptional(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <AuthContext.Provider value={mockValue}>{children}</AuthContext.Provider>
      ),
    });
    expect(result.current?.status).toBe('authenticated');
  });

  it('在 Provider 外返回 null（不抛错）', () => {
    const { result } = renderHook(() => useAuthOptional());
    expect(result.current).toBeNull();
  });
});
