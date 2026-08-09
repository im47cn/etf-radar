import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

// ── Mock auth ──────────────────────────────────────────────────────────────
let mockAuthStatus: string = 'authenticated';
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ status: mockAuthStatus, user: { id: 'u1' } }),
  useAuthOptional: () => ({ status: mockAuthStatus, user: { id: 'u1' } }),
}));

// ── Mock useWatchlist ──────────────────────────────────────────────────────
// 直接 mock hook 返回值，避免 supabase 异步链导致 OOM
let mockAdd: ReturnType<typeof vi.fn>;
vi.mock('@/lib/watchlist/useWatchlist', () => ({
  useWatchlist: () => ({
    items: [],
    loading: false,
    error: null,
    refresh: vi.fn(),
    add: mockAdd,
    remove: vi.fn(),
  }),
}));

import { AddWatchButton } from '@/components/membership/AddWatchButton';

describe('AddWatchButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthStatus = 'authenticated';
    mockAdd = vi.fn();
  });

  const renderButton = (props: React.ComponentProps<typeof AddWatchButton>) =>
    render(
      <MemoryRouter>
        <AddWatchButton {...props} />
      </MemoryRouter>,
    );

  it('未认证 → 点击不抛错（导航到 /membership）', async () => {
    mockAuthStatus = 'anonymous';
    const user = userEvent.setup();
    renderButton({ itemType: 'theme', itemKey: 'semi' });
    await user.click(screen.getByText('＋自选'));
    expect(mockAdd).not.toHaveBeenCalled();
  });

  it('已认证 + 成功 → 显示"已加入自选"', async () => {
    mockAdd.mockResolvedValue({ error: null });
    const user = userEvent.setup();
    renderButton({ itemType: 'theme', itemKey: 'semi' });
    await user.click(screen.getByText('＋自选'));
    await waitFor(() => {
      expect(screen.getByText('已加入自选')).toBeInTheDocument();
    });
  });

  it('已认证 + 失败 → 显示失败消息', async () => {
    mockAdd.mockResolvedValue({ error: 'RPC错误' });
    const user = userEvent.setup();
    renderButton({ itemType: 'theme', itemKey: 'semi' });
    await user.click(screen.getByText('＋自选'));
    await waitFor(() => {
      expect(screen.getByText(/失败：RPC错误/)).toBeInTheDocument();
    });
  });

  it('已认证 + NotAMemberError → 显示"自选为会员功能"', async () => {
    const { NotAMemberError } = await import('@/lib/watchlist/types');
    mockAdd.mockRejectedValue(new NotAMemberError());
    const user = userEvent.setup();
    renderButton({ itemType: 'theme', itemKey: 'semi' });
    await user.click(screen.getByText('＋自选'));
    await waitFor(() => {
      expect(screen.getByText('自选为会员功能')).toBeInTheDocument();
    });
  });

  it('已认证 + 未知异常 → 显示"操作失败"', async () => {
    mockAdd.mockRejectedValue(new Error('网络断开'));
    const user = userEvent.setup();
    renderButton({ itemType: 'theme', itemKey: 'semi' });
    await user.click(screen.getByText('＋自选'));
    await waitFor(() => {
      expect(screen.getByText('操作失败')).toBeInTheDocument();
    });
  });

  it('busy 态: 点击后按钮先显示"..."再显示结果', async () => {
    mockAdd.mockImplementation(() => new Promise((r) => setTimeout(() => r({ error: null }), 10)));
    const user = userEvent.setup();
    renderButton({ itemType: 'theme', itemKey: 'semi' });
    await user.click(screen.getByText('＋自选'));
    await waitFor(() => {
      expect(screen.getByText('已加入自选')).toBeInTheDocument();
    });
  });

  it('自定义 className 应用到按钮', () => {
    renderButton({ itemType: 'theme', itemKey: 'semi', className: 'my-btn' });
    const btn = screen.getByText('＋自选').closest('button');
    expect(btn?.className).toContain('my-btn');
  });
});
