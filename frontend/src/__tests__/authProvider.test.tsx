import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// ── Mock Supabase ──────────────────────────────────────────────────────────
const mockGetSession = vi.fn();
const mockOnAuthStateChange = vi.fn();
const mockSignInWithOtp = vi.fn();
const mockSignInWithOAuth = vi.fn();
const mockSignOut = vi.fn();

const mockSupabase = {
  auth: {
    getSession: mockGetSession,
    onAuthStateChange: mockOnAuthStateChange,
    signInWithOtp: mockSignInWithOtp,
    signInWithOAuth: mockSignInWithOAuth,
    signOut: mockSignOut,
  },
};

let configured = true;
vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => configured,
  getSupabase: () => mockSupabase,
}));

import { AuthProvider } from '@/providers/AuthProvider';
import { useAuth } from '@/hooks/useAuth';

// 子组件：消费 context 并暴露各方法返回值
const Consumer = ({ onReady }: { onReady?: (ctx: ReturnType<typeof useAuth>) => void }) => {
  const ctx = useAuth();
  React.useEffect(() => {
    onReady?.(ctx);
  }, [onReady]);
  return <div data-testid="consumer">{ctx.status}</div>;
};

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    configured = true;
    mockGetSession.mockResolvedValue({ data: { session: null } });
    mockOnAuthStateChange.mockReturnValue({
      data: { subscription: { unsubscribe: vi.fn() } },
    });
    mockSignInWithOtp.mockResolvedValue({ error: null });
    mockSignInWithOAuth.mockResolvedValue({ error: null });
    mockSignOut.mockResolvedValue({});
  });

  it('unconfigured 时 status=unconfigured, 不调 supabase', () => {
    configured = false;
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    expect(screen.getByText('unconfigured')).toBeInTheDocument();
    expect(mockGetSession).not.toHaveBeenCalled();
  });

  it('configured + 无 session → status=anonymous', async () => {
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByText('anonymous')).toBeInTheDocument();
    });
    expect(mockGetSession).toHaveBeenCalled();
  });

  it('configured + 有 session → status=authenticated', async () => {
    const mockUser = { id: 'u1', email: 'a@b.com' };
    mockGetSession.mockResolvedValue({ data: { session: { user: mockUser } } });
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByText('authenticated')).toBeInTheDocument();
    });
  });

  it('signInWithMagicLink 调 signInWithOtp 并返回 error', async () => {
    let ctxRef: ReturnType<typeof useAuth> | null = null;
    render(
      <AuthProvider>
        <Consumer onReady={(c) => { ctxRef = c; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctxRef).not.toBeNull());
    const r = await ctxRef!.signInWithMagicLink('test@example.com');
    expect(mockSignInWithOtp).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'test@example.com' }),
    );
    expect(r.error).toBeNull();
  });

  it('signInWithMagicLink 返回错误消息', async () => {
    mockSignInWithOtp.mockResolvedValue({ error: { message: '邮箱无效' } });
    let ctxRef: ReturnType<typeof useAuth> | null = null;
    render(
      <AuthProvider>
        <Consumer onReady={(c) => { ctxRef = c; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctxRef).not.toBeNull());
    const r = await ctxRef!.signInWithMagicLink('bad@example.com');
    expect(r.error).toBe('邮箱无效');
  });

  it('signInWithGoogle 调 signInWithOAuth', async () => {
    let ctxRef: ReturnType<typeof useAuth> | null = null;
    render(
      <AuthProvider>
        <Consumer onReady={(c) => { ctxRef = c; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctxRef).not.toBeNull());
    const r = await ctxRef!.signInWithGoogle();
    expect(mockSignInWithOAuth).toHaveBeenCalledWith(
      expect.objectContaining({ provider: 'google' }),
    );
    expect(r.error).toBeNull();
  });

  it('signInWithGithub 调 signInWithOAuth', async () => {
    let ctxRef: ReturnType<typeof useAuth> | null = null;
    render(
      <AuthProvider>
        <Consumer onReady={(c) => { ctxRef = c; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctxRef).not.toBeNull());
    const r = await ctxRef!.signInWithGithub();
    expect(mockSignInWithOAuth).toHaveBeenCalledWith(
      expect.objectContaining({ provider: 'github' }),
    );
    expect(r.error).toBeNull();
  });

  it('signOut 调 supabase.auth.signOut', async () => {
    let ctxRef: ReturnType<typeof useAuth> | null = null;
    render(
      <AuthProvider>
        <Consumer onReady={(c) => { ctxRef = c; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctxRef).not.toBeNull());
    await ctxRef!.signOut();
    expect(mockSignOut).toHaveBeenCalled();
  });

  it('unconfigured 时 signIn 返回未配置错误', async () => {
    configured = false;
    let ctxRef: ReturnType<typeof useAuth> | null = null;
    render(
      <AuthProvider>
        <Consumer onReady={(c) => { ctxRef = c; }} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctxRef).not.toBeNull());
    const r = await ctxRef!.signInWithMagicLink('a@b.com');
    expect(r.error).toBe('未配置 Supabase');
  });
});
