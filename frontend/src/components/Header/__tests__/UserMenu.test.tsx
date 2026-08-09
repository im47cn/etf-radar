import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { UserMenu } from '../UserMenu';
import { useAuth } from '@/hooks/useAuth';

vi.mock('@/hooks/useAuth');

const renderMenu = () =>
  render(
    <MemoryRouter>
      <UserMenu />
    </MemoryRouter>,
  );

describe('UserMenu', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders nothing when loading', () => {
    vi.mocked(useAuth).mockReturnValue({ status: 'loading' } as never);
    const { container } = renderMenu();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when unconfigured', () => {
    vi.mocked(useAuth).mockReturnValue({ status: 'unconfigured' } as never);
    const { container } = renderMenu();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows membership + login links side by side when anonymous', () => {
    vi.mocked(useAuth).mockReturnValue({ status: 'anonymous' } as never);
    renderMenu();
    expect(screen.getByText('会员').closest('a')).toHaveAttribute('href', '/membership');
    expect(screen.getByText('登录').closest('a')).toHaveAttribute('href', '/portfolio');
    // 未登录态不渲染退出登录
    expect(screen.queryByText('退出登录')).toBeNull();
  });

  it('shows membership entry above logout inside the dropdown when authenticated', () => {
    const signOut = vi.fn();
    vi.mocked(useAuth).mockReturnValue({
      status: 'authenticated',
      user: { email: 'a@b.com' },
      signOut,
    } as never);
    renderMenu();

    // 默认收起，展开下拉
    fireEvent.click(screen.getByRole('button'));
    const membership = screen.getByText('会员').closest('a');
    const logout = screen.getByText('退出登录');
    expect(membership).toHaveAttribute('href', '/membership');

    // 会员项应排在退出登录之前（DOM 顺序）
    expect(membership!.compareDocumentPosition(logout)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    // 点击会员关闭下拉
    fireEvent.click(membership!);
    expect(screen.queryByText('退出登录')).toBeNull();
  });

  it('signs out on logout click', () => {
    const signOut = vi.fn();
    vi.mocked(useAuth).mockReturnValue({
      status: 'authenticated',
      user: { email: 'a@b.com' },
      signOut,
    } as never);
    renderMenu();
    fireEvent.click(screen.getByRole('button'));
    fireEvent.click(screen.getByText('退出登录'));
    expect(signOut).toHaveBeenCalledOnce();
  });
});
