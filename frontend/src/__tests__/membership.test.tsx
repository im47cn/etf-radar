import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

// Mock useSubscription — 覆盖 loading/member/non-member 三个分支
const mockUseSubscription = vi.fn();
vi.mock('@/lib/subscription/useSubscription', () => ({
  useSubscription: () => mockUseSubscription(),
}));

// Mock getSupabase — BindCodeBlock 的 RPC 调用
const mockRpc = vi.fn();
vi.mock('@/lib/supabase', () => ({
  getSupabase: () => ({ rpc: mockRpc }),
  isSupabaseConfigured: () => true,
}));

import { Disclaimer } from '@/components/membership/Disclaimer';
import { MembershipPanel } from '@/components/membership/MembershipPanel';

const wrap = (ui: React.ReactElement) =>
  render(<MemoryRouter>{ui}</MemoryRouter>);

describe('Disclaimer', () => {
  it('渲染免责声明文本', () => {
    render(<Disclaimer />);
    expect(screen.getByText(/非投资建议/)).toBeInTheDocument();
  });
});

describe('MembershipPanel', () => {
  it('loading 态显示加载文本', () => {
    mockUseSubscription.mockReturnValue({ state: 'loading' });
    mockRpc.mockResolvedValue({ data: 'CODE123', error: null });
    wrap(<MembershipPanel />);
    expect(screen.getByText('加载订阅状态...')).toBeInTheDocument();
  });

  it('member 态显示会员生效中 + 隐藏定价卡', () => {
    mockUseSubscription.mockReturnValue({
      state: 'member',
      plan: 'monthly',
      periodEnd: '2026-12-31T00:00:00Z',
    });
    mockRpc.mockResolvedValue({ data: 'CODE', error: null });
    wrap(<MembershipPanel />);
    expect(screen.getByText(/会员生效中/)).toBeInTheDocument();
    expect(screen.queryByText('月度会员')).toBeNull();
  });

  it('non-member 态显示定价卡 + 功能对比', async () => {
    mockUseSubscription.mockReturnValue({ state: 'non-member' });
    mockRpc.mockResolvedValue({ data: 'BINDCODE', error: null });
    wrap(<MembershipPanel />);
    expect(screen.getByText('月度会员')).toBeInTheDocument();
    expect(screen.getByText('年度会员')).toBeInTheDocument();
    expect(screen.getByText('功能')).toBeInTheDocument();
    expect(screen.getAllByText(/市场温度/).length).toBeGreaterThan(0);
    // BindCodeBlock 异步加载绑定码
    await waitFor(() => {
      expect(screen.getByText('BINDCODE')).toBeInTheDocument();
    });
  });

  it('non-member + RPC error 显示生成失败', async () => {
    mockUseSubscription.mockReturnValue({ state: 'non-member' });
    mockRpc.mockResolvedValue({ data: null, error: { message: '网络错误' } });
    wrap(<MembershipPanel />);
    await waitFor(() => {
      expect(screen.getByText(/生成失败/)).toBeInTheDocument();
    });
  });
});
