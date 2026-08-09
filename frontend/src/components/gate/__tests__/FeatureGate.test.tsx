import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { FeatureGate, GATE_COPY } from '../FeatureGate';
import { AuthContext } from '@/providers/authContext';

vi.mock('@/lib/subscription/useSubscription', () => ({
  useSubscription: vi.fn(),
}));

import { useSubscription } from '@/lib/subscription/useSubscription';

type AuthStatus = 'loading' | 'anonymous' | 'authenticated' | 'unconfigured';
type SubState = 'loading' | 'member' | 'non-member';

const renderGate = (
  props: { copy: 'portfolio' | 'evidence'; required: 'auth' | 'member' },
  authStatus: AuthStatus,
  subState: SubState = 'non-member',
) => {
  vi.mocked(useSubscription).mockReturnValue({ state: subState } as never);
  render(
    <MemoryRouter>
      <AuthContext.Provider
        value={
          {
            status: authStatus,
            user: authStatus === 'authenticated' ? { email: 'a@b.com' } : null,
          } as never
        }
      >
        <FeatureGate {...props}>
          <div>protected</div>
        </FeatureGate>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
};

describe('FeatureGate 状态路由', () => {
  it('loading → 骨架，不渲染 children', () => {
    renderGate({ copy: 'evidence', required: 'member' }, 'loading');
    expect(screen.getByText('加载中...')).toBeInTheDocument();
    expect(screen.queryByText('protected')).toBeNull();
  });

  it('unconfigured → 配置缺失卡，功能名按 copy', () => {
    renderGate({ copy: 'evidence', required: 'member' }, 'unconfigured');
    expect(screen.getByText(/未配置 Supabase/)).toBeInTheDocument();
    expect(screen.getByText(/信号证据功能需要 Supabase/)).toBeInTheDocument();
  });

  it('anonymous → hero 登录表单 + features，children 隐藏', () => {
    renderGate({ copy: 'evidence', required: 'member' }, 'anonymous');
    expect(screen.getByText('信号证据')).toBeInTheDocument();
    expect(screen.getByText(/5 年样本外 IC/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /发送登录链接/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Google/ })).toBeInTheDocument();
    expect(screen.queryByText('protected')).toBeNull();
  });

  it('authenticated + required=auth → 直接渲染 children', () => {
    renderGate({ copy: 'portfolio', required: 'auth' }, 'authenticated');
    expect(screen.getByText('protected')).toBeInTheDocument();
  });

  it('authenticated + required=member + sub=loading → 骨架', () => {
    renderGate({ copy: 'evidence', required: 'member' }, 'authenticated', 'loading');
    expect(screen.getByText('加载中...')).toBeInTheDocument();
    expect(screen.queryByText('protected')).toBeNull();
  });

  it('authenticated + required=member + member → 渲染 children', () => {
    renderGate({ copy: 'evidence', required: 'member' }, 'authenticated', 'member');
    expect(screen.getByText('protected')).toBeInTheDocument();
  });

  it('authenticated + required=member + non-member → hero 升级卡', () => {
    renderGate({ copy: 'evidence', required: 'member' }, 'authenticated', 'non-member');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText('立即开通会员').closest('a')).toHaveAttribute('href', '/membership');
    expect(screen.getByText(/5 年样本外 IC/)).toBeInTheDocument();
  });
});

describe('FeatureGate 登录交互', () => {
  it('magic link 登录调用 signInWithMagicLink', async () => {
    const signInWithMagicLink = vi.fn().mockResolvedValue({ error: null });
    vi.mocked(useSubscription).mockReturnValue({ state: 'non-member' } as never);
    render(
      <MemoryRouter>
        <AuthContext.Provider
          value={
            {
              status: 'anonymous',
              user: null,
              signInWithMagicLink,
              signInWithGoogle: vi.fn(),
              signInWithGithub: vi.fn(),
            } as never
          }
        >
          <FeatureGate copy="evidence" required="member">
            <div>protected</div>
          </FeatureGate>
        </AuthContext.Provider>
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/邮箱登录/), { target: { value: 'test@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: /发送登录链接/ }));
    await vi.waitFor(() => expect(signInWithMagicLink).toHaveBeenCalledWith('test@example.com'));
  });
});

describe('GATE_COPY', () => {
  it('4 个门控页均有 ≥3 条 features', () => {
    const keys = Object.keys(GATE_COPY);
    expect(keys).toEqual(['portfolio', 'watchlist', 'evidence', 'membership']);
    for (const k of keys) {
      expect(GATE_COPY[k as keyof typeof GATE_COPY].features.length).toBeGreaterThanOrEqual(3);
    }
  });
});
