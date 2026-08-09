import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AuthGate } from '../AuthGate';
import { AuthContext } from '@/providers/authContext';

const renderWithAuth = (status: 'loading' | 'anonymous' | 'unconfigured', overrides = {}) => {
  const value = {
    status,
    user: null,
    signInWithMagicLink: vi.fn().mockResolvedValue({ error: null }),
    signInWithGoogle:    vi.fn().mockResolvedValue({ error: null }),
    signInWithGithub:    vi.fn().mockResolvedValue({ error: null }),
    signOut:             vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(
    <AuthContext.Provider value={value as never}>
      <AuthGate><div>protected</div></AuthGate>
    </AuthContext.Provider>
  );
  return value;
};

describe('AuthGate', () => {
  it('loading: shows skeleton, not children', () => {
    renderWithAuth('loading');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText(/加载中/)).toBeInTheDocument();
  });

  it('anonymous: shows login card', () => {
    renderWithAuth('anonymous');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText(/持仓信号监控/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /发送登录链接/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Google/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /GitHub/ })).toBeInTheDocument();
  });

  it('unconfigured: shows config-missing message', () => {
    renderWithAuth('unconfigured');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText(/未配置 Supabase/)).toBeInTheDocument();
    expect(screen.getByText(/持仓监控功能需要 Supabase/)).toBeInTheDocument();
  });

  it('unconfigured: renders hint by copy key (evidence)', () => {
    render(
      <AuthContext.Provider value={{ status: 'unconfigured', user: null } as never}>
        <AuthGate copy="evidence">
          <div>protected</div>
        </AuthGate>
      </AuthContext.Provider>,
    );
    expect(screen.getByText(/信号证据功能需要 Supabase/)).toBeInTheDocument();
    expect(screen.queryByText(/持仓监控功能/)).toBeNull();
  });

  it('anonymous: renders title/subtitle/privacyNote by copy key (membership)', () => {
    render(
      <AuthContext.Provider value={{ status: 'anonymous', user: null } as never}>
        <AuthGate copy="membership">
          <div>protected</div>
        </AuthGate>
      </AuthContext.Provider>,
    );
    expect(screen.getByText('💳 会员订阅')).toBeInTheDocument();
    expect(screen.getByText('登录后查看与管理您的会员订阅')).toBeInTheDocument();
    expect(screen.getByText(/订阅数据仅用于会员服务/)).toBeInTheDocument();
    // 默认持仓文案不应出现
    expect(screen.queryByText(/持仓信号监控/)).toBeNull();
  });

  it('magic link: calls signInWithMagicLink with input', async () => {
    const { signInWithMagicLink } = renderWithAuth('anonymous');
    const input = screen.getByLabelText(/邮箱/);
    fireEvent.change(input, { target: { value: 'test@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: /发送登录链接/ }));
    expect(signInWithMagicLink).toHaveBeenCalledWith('test@example.com');
  });
});
