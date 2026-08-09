import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MemberGate } from '../MemberGate';

vi.mock('@/lib/subscription/useSubscription', () => ({
  useSubscription: vi.fn(),
}));

import { useSubscription } from '@/lib/subscription/useSubscription';

const renderGate = (subState: 'loading' | 'member' | 'non-member') => {
  vi.mocked(useSubscription).mockReturnValue({ state: subState } as never);
  render(
    <MemoryRouter>
      <MemberGate>
        <div>protected</div>
      </MemberGate>
    </MemoryRouter>,
  );
};

describe('MemberGate', () => {
  it('loading: 显示骨架，不渲染 children', () => {
    renderGate('loading');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText(/加载中/)).toBeInTheDocument();
  });

  it('member: 渲染 children', () => {
    renderGate('member');
    expect(screen.getByText('protected')).toBeInTheDocument();
    expect(screen.queryByText('会员专属')).toBeNull();
  });

  it('non-member: 显示默认（自选盯盘）升级引导', () => {
    renderGate('non-member');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText('会员专属')).toBeInTheDocument();
    expect(screen.getByText(/自选盯盘为会员功能/)).toBeInTheDocument();
    expect(screen.getByText('前往开通').closest('a')).toHaveAttribute('href', '/membership');
  });

  it('non-member: 按 copy key 渲染文案 (evidence)', () => {
    vi.mocked(useSubscription).mockReturnValue({ state: 'non-member' } as never);
    render(
      <MemoryRouter>
        <MemberGate copy="evidence">
          <div>protected</div>
        </MemberGate>
      </MemoryRouter>,
    );
    expect(screen.getByText(/信号证据为会员功能/)).toBeInTheDocument();
    expect(screen.getByText(/5 年样本外统计有效性的可视化证据/)).toBeInTheDocument();
    expect(screen.queryByText(/自选盯盘/)).toBeNull();
  });
});
