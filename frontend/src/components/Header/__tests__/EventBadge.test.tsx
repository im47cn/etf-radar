import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EventBadge } from '../EventBadge';

const eventsMock = vi.fn();
vi.mock('@/hooks/useUserEvents', () => ({
  useUserEvents: () => eventsMock(),
}));

const rWith = (count: number) => {
  eventsMock.mockReturnValue({ unreadCount: count, events: [] });
  return render(<MemoryRouter><EventBadge /></MemoryRouter>);
};

describe('EventBadge', () => {
  it('未读 0 时不显示徽章', () => {
    rWith(0);
    expect(screen.queryByTestId('event-badge')).not.toBeInTheDocument();
  });
  it('未读 > 0 时显示数字', () => {
    rWith(3);
    expect(screen.getByTestId('event-badge').textContent).toBe('3');
  });
  it('未读 > 99 显示 99+', () => {
    rWith(150);
    expect(screen.getByTestId('event-badge').textContent).toBe('99+');
  });
});
